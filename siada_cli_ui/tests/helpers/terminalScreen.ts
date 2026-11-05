import stringWidth from 'string-width';

/** A cell-based VT screen for Ink's cursor moves, erase operations and ONLCR. */
export class TerminalScreen {
  private cells: string[][];
  private row = 0;
  private column = 0;
  private pendingWrap = false;
  private autoWrap = true;
  private buffer = '';
  private scrollback: string[] = [];
  constructor(
    readonly rows: number,
    readonly columns: number,
    private characterWidth: (character: string) => number = stringWidth,
    private legacyWideWrap = false,
  ) {
    this.cells = Array.from({ length: rows }, () => Array(columns).fill(' '));
  }
  private newline() {
    this.pendingWrap = false;
    if (++this.row >= this.rows) {
      this.scrollback.push(this.cells.shift()!.join('').trimEnd());
      this.cells.push(Array(this.columns).fill(' ')); this.row = this.rows - 1;
    }
  }
  feed(raw: string) {
    this.buffer += raw;
    let index = 0;
    while (index < this.buffer.length) {
      const character = String.fromCodePoint(this.buffer.codePointAt(index)!);
      if (character === '\x1b') {
        const rest = this.buffer.slice(index);
        const csi = /^\x1b\[([0-9;?<=>]*)([@-~])/.exec(rest);
        if (csi) {
          if (csi[1] === '?7' && (csi[2] === 'h' || csi[2] === 'l')) {
            this.autoWrap = csi[2] === 'h';
            this.pendingWrap = false;
          }
          const [a = 0, b = 0] = csi[1].replace(/[?<=>]/g, '').split(';').map(Number);
          switch (csi[2]) {
            case 'A': this.row = Math.max(0, this.row - (a || 1)); break;
            case 'B': this.row = Math.min(this.rows - 1, this.row + (a || 1)); break;
            case 'E': this.row = Math.min(this.rows - 1, this.row + (a || 1)); this.column = 0; break;
            case 'F': this.row = Math.max(0, this.row - (a || 1)); this.column = 0; break;
            case 'C': this.column = Math.min(this.columns - 1, this.column + (a || 1)); break;
            case 'D': this.column = Math.max(0, this.column - (a || 1)); break;
            case 'G': this.column = Math.max(0, (a || 1) - 1); break;
            case 'H': case 'f': this.row = (a || 1) - 1; this.column = (b || 1) - 1; break;
            case 'J':
              if (a === 3) this.scrollback = [];
              else if (a === 2) this.cells.forEach(line => line.fill(' '));
              else {
                this.cells[this.row].fill(' ', this.column);
                this.cells.slice(this.row + 1).forEach(line => line.fill(' '));
              }
              break;
            case 'K':
              this.cells[this.row].fill(' ', a === 2 ? 0 : this.column, a === 1 ? this.column + 1 : this.columns);
              break;
          }
          if (!['m', 'h', 'l'].includes(csi[2])) this.pendingWrap = false;
          index += csi[0].length; continue;
        }
        if (rest.startsWith('\x1b]')) {
          const end = /\x07|\x1b\\/.exec(rest);
          if (!end) break;
          index += end.index + end[0].length; continue;
        }
        if (rest.startsWith('\x1bc')) {
          this.cells.forEach(line => line.fill(' ')); this.row = 0; this.column = 0; this.pendingWrap = false;
          this.scrollback = [];
          index += 2; continue;
        }
        if (rest.length < 3 || rest.startsWith('\x1b[')) break;
        index += 2; continue;
      }
      if (character === '\n') { this.newline(); this.column = 0; }
      else if (character === '\r') { this.column = 0; this.pendingWrap = false; }
      else if (character >= ' ') {
        const width = this.characterWidth(character);
        if (this.legacyWideWrap && width === 2 && this.column + width > this.columns) {
          this.newline(); this.column = 0;
        }
        if (this.autoWrap && (this.pendingWrap || this.column + width > this.columns)) { this.newline(); this.column = 0; }
        if (!this.autoWrap && this.column + width > this.columns) {
          this.column = Math.max(0, this.columns - width);
        }
        if (width > 0) {
          this.cells[this.row][this.column] = character;
          if (width === 2) this.cells[this.row][this.column + 1] = '';
          this.column += width;
          if (this.column >= this.columns) { this.column = this.columns - 1; this.pendingWrap = this.autoWrap; }
        }
      }
      index += character.length;
    }
    this.buffer = this.buffer.slice(index);
  }
  display() { return this.cells.map(line => line.join('').trimEnd()).join('\n'); }
  history() { return this.scrollback.join('\n'); }
  transcript() { return this.history() + '\n' + this.display(); }
}