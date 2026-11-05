// Keep DEC modes separate: JediTerm may only apply the first CSI parameter.
// Pointer capture owns wheel input, so disable alternate-screen arrow synthesis.
export const ENABLE_MOUSE_TRACKING =
  '\x1b[?1007l\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h';

// Release pointer capture without enabling synthetic arrow input during teardown.
export const DISABLE_MOUSE_TRACKING =
  '\x1b[?1003l\x1b[?1002l\x1b[?1000l\x1b[?1006l\x1b[?1007l';