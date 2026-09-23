// One bounded HWP/HWPX buffer in, one JSON report out. No filePath / CLI / MCP.
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { lockDown } from './guard.mjs';

const MAX_INPUT = 50_000_000;
const MAX_TEXT = 200_000;
const MAX_OUTPUT = 4_000_000;
const MAX_FRAGMENTS = 20_000;

function fail(code) { throw new Error(code); }
function text(value) {
  if (value === undefined) return '';
  if (typeof value !== 'string' || value.length > MAX_TEXT) fail('text_limit');
  return value;
}

async function main() {
  lockDown();
  const metadata = JSON.parse(await readFile(new URL('./node_modules/kordoc/package.json', import.meta.url), 'utf8'));
  if (metadata.version !== '4.14.1') fail('version_mismatch');
  // Library diagnostics never enter stdout or expose document contents to logs.
  console.log = console.warn = console.error = () => {};
  const chunks = [];
  let length = 0;
  for await (const chunk of process.stdin) {
    length += chunk.length;
    if (length > MAX_INPUT) fail('input_limit');
    chunks.push(chunk);
  }
  const buffer = Buffer.concat(chunks);
  if (!buffer.length) fail('empty_input');
  const { parse } = await import('kordoc');
  const result = await parse(buffer, {
    ocr: false, formulaOcr: false, keepTrailingEmptyCols: true,
    keepEmptyParagraphs: true, classifyTables: false, dedupeRunningHeaders: false,
  });
  if (!result.success) fail('parse_failed');
  if (!['hwp', 'hwpx'].includes(result.fileType)) fail('unsupported_format');
  const warnings = (result.warnings || []).map(w => String(w.code || 'UNKNOWN').slice(0, 80));
  if (warnings.some(code => ['DRM_COM_FALLBACK', 'COM_EMPTY'].includes(code))) fail('com_result_rejected');
  if (result.markdown.includes('상위 버전의 배포용 문서')) fail('protected_document');
  const pageMode = ['layout', 'section'].includes(result.metadata?.pageMode) ? result.metadata.pageMode : 'unknown';
  const fragments = [], tables = [], plain = [];
  let chars = 0;
  function add(fragment) {
    chars += fragment.text.length;
    if (chars > 1_000_000 || fragments.length >= MAX_FRAGMENTS) fail('fragment_limit');
    fragments.push(fragment);
  }
  function visit(blocks, path, inheritedPage = null, depth = 0, collectText = true) {
    if (!Array.isArray(blocks) || depth > 20) fail('structure_limit');
    for (let i = 0; i < blocks.length; i++) {
      const block = blocks[i], locator = `${path}/${i}`;
      const page = pageMode === 'layout' && Number.isSafeInteger(block.pageNumber) && block.pageNumber > 0
        ? block.pageNumber : inheritedPage;
      if (block.text !== undefined) {
        const value = text(block.text);
        add({ locator, kind: 'paragraph', text: value, page });
        if (collectText) plain.push(value);
      }
      if (block.table) {
        const table = block.table;
        if (tables.length >= 100 || !Number.isInteger(table.rows) || !Number.isInteger(table.cols) ||
            table.rows < 1 || table.rows > 2000 || table.cols < 1 || table.cols > 128 ||
            table.rows * table.cols > 20_000 || !Array.isArray(table.cells)) fail('table_limit');
        tables.push({ locator, rows: table.rows, cols: table.cols, source_id: table.sourceId ? String(table.sourceId) : null, page });
        for (let row = 0; row < table.cells.length; row++) {
          if (row >= table.rows || !Array.isArray(table.cells[row])) fail('invalid_table');
          for (let col = 0; col < table.cells[row].length; col++) {
            if (col >= table.cols) fail('invalid_table');
            const cell = table.cells[row][col];
            const value = text(cell.text), cellPath = `${locator}/cells/${row}/${col}`;
            add({ locator: cellPath, kind: 'table_cell', text: value, page,
              table_locator: locator, row, col, row_span: cell.rowSpan, col_span: cell.colSpan });
            if (collectText) plain.push(value);
            if (cell.blocks) visit(cell.blocks, `${cellPath}/blocks`, page, depth + 1, false);
          }
        }
        if (table.captionBlocks) visit(table.captionBlocks, `${locator}/caption`, page, depth + 1, collectText);
        else if (table.caption) {
          const value = text(table.caption);
          add({ locator: `${locator}/caption`, kind: 'paragraph', text: value, page });
          if (collectText) plain.push(value);
        }
      }
      if (block.children) visit(block.children, `${locator}/children`, page, depth + 1, collectText);
    }
  }
  visit(result.blocks, 'blocks');
  const output = JSON.stringify({ contract_version: 1, engine_version: metadata.version,
    source_sha256: createHash('sha256').update(buffer).digest('hex'), format: result.fileType,
    page_mode: pageMode, text: text(plain.join('\n')), markdown: text(result.markdown),
    fragments, tables, warnings: [...new Set(warnings)], review_required: true, verified: false });
  if (Buffer.byteLength(output) > MAX_OUTPUT) fail('output_limit');
  process.stdout.write(output);
}

main().catch(error => {
  const allowed = new Set(['permission_required', 'version_mismatch', 'empty_input', 'input_limit',
    'text_limit', 'parse_failed', 'unsupported_format', 'com_result_rejected', 'protected_document',
    'fragment_limit', 'structure_limit', 'table_limit', 'invalid_table', 'output_limit']);
  process.stdout.write(JSON.stringify({ error_code: allowed.has(error.message) ? error.message : 'parser_failed' }));
  process.exitCode = 1;
});
