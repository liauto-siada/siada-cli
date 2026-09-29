// ASCII-art ghost logo, replicated from https://ghostty.org/ hero animation.
// Each row is a list of [text, isAccent] segments; accent segments are
// rendered in Ghostty's brand blue, the rest in the default terminal color.

type Segment = readonly [text: string, isAccent: boolean];

const GHOST_ROWS: readonly Segment[][] = [
  [["                          ", false], ["x+++++++==++++++++", true], ["                          ", false]],
  [["                    ", false], ["++++*******%%%**%%%*%*%****=++", true], ["                    ", false]],
  [["                ", false], ["xx==**=*++", true], ["                    ", false], ["==****++", true], ["                ", false]],
  [["              ", false], ["++**+=", true], ["                              ", false], ["++*=**++", true], ["            ", false]],
  [["          ", false], ["xx====oo", true], ["        ~+*$$@@@@@@@@@@$%=o         ", false], ["+x*=++", true], ["          ", false]],
  [["        ", false], ["x+===+", true], ["       ·=@@@@@@@$$$$$$$$$$$$@@@@@@%o       ", false], ["~====", true], ["        ", false]],
  [["        ", false], ["===+", true], ["      o$@@@$$$$$$$$$$$$$$$$$$$$$$$$$@@@@=       ", false], ["==++", true], ["      ", false]],
  [["      ", false], ["==++", true], ["      %@@@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@@$~      ", false], ["==++", true], ["    ", false]],
  [["    ", false], ["++==", true], ["      %@@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@@~    ", false], ["~+==", true], ["    ", false]],
  [["    ", false], ["==+o", true], ["    +@@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@%     ", false], ["++++", true], ["  ", false]],
  [["  ", false], ["xx==", true], ["     $@$$$$@@@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@@    ", false], ["·x==", true], ["  ", false]],
  [["  ", false], ["+++x", true], ["    @@$$$@@%=*@@@@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==xx", true]],
  [["  ", false], ["==", true], ["     %@$$$$*      ~*@@@@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@    ", false], ["x+++", true]],
  [["  ", false], ["==", true], ["     @$$$$@=          o*@@@$$$$$$$@@@@@@@@@@@@@@@@@@$$$$$$+   ", false], ["·+==", true]],
  [["ox==", true], ["    =$$$$$$@%·            o@$$$$$@o                +@$$$$$$     ", false], ["==", true]],
  [["ox++", true], ["    %@$$$$$$$@@@%·          @$$$@                    @$$$$@     ", false], ["==", true]],
  [["ox++", true], ["    %@$$$$$@@@*~           ~@$$$@~                  +@$$$$@     ", false], ["==", true]],
  [["ox++", true], ["    %@$$$$$$            ·=@@$$$$$@@***************%@@$$$$$@     ", false], ["==", true]],
  [["ox++", true], ["    %@$$$$@+         =$@@@$$$$$$$$$@@@@@@@@@@@@@@@@$$$$$$$@     ", false], ["==", true]],
  [["ox++", true], ["    %@$$$$$$x    =$@@@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["ox++", true], ["    %@$$$$$$@@@@@@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["ox++", true], ["    *@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["ox==", true], ["    *@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["ox==", true], ["    *@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["ox==", true], ["    =@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["ox==", true], ["    =@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["ox==", true], ["    =@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["ox==", true], ["    +@$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["  ", false], ["==", true], ["    +$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$     ", false], ["==", true]],
  [["  ", false], ["==", true], ["     @$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$@     ", false], ["==", true]],
  [["  ", false], ["==x", true], ["     @@@$$$$$$$$$@@@@@@@@@$$$$$$$$$$@@@@@@@@@$$$$$$$$$@@$    ", false], ["·+==", true]],
  [["  ", false], ["++++", true], ["     ·*@@@@@@@@@%o      +@@@@@@@@@@=      ~%@@@@@@@@@*      ", false], ["==+x", true]],
  [["    ", false], ["===x", true], ["        ·~·                ~~                ·~·        ", false], ["++==", true], ["  ", false]],
  [["      ", false], ["==++", true], ["              ", false], ["x+%%", true], ["                ", false], ["%%+x", true], ["              ", false], ["++==", true], ["    ", false]],
  [["        ", false], ["++**=*++xoox==*===++===%==xoox==%=**+++=*%=*+xox++*=**++", true], ["      ", false]],
  [["            ", false], ["+++++==+++", true], ["          ", false], ["+++==+++", true], ["          ", false], ["++====++++", true], ["          ", false]],
];

// Ghostty's brand blue (rgb(53, 81, 243))
const ACCENT_COLOR = "\x1b[38;2;53;81;243m";
const RESET = "\x1b[0m";

/**
 * Renders the ghost logo as an array of lines with ANSI color codes,
 * ready to be printed with console.log.
 */
export function renderGhostLogo(useColor = true): string[] {
  return GHOST_ROWS.map((segments) =>
    segments
      .map(([text, isAccent]) =>
        isAccent && useColor ? `${ACCENT_COLOR}${text}${RESET}` : text,
      )
      .join(""),
  );
}
