/** Server ranges are Unicode codepoints, never JavaScript UTF-16 offsets. */
export function codepointSlice(text: string, start: number, end: number): string {
  return codepointSlicer(text)(start, end);
}

export function codepointSlicer(text: string): (start: number, end: number) => string {
  const points = Array.from(text);
  return (start, end) => points.slice(Math.max(0, start), end).join("");
}
