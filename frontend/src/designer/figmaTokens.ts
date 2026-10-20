import type { FigDocument } from 'openfig-core';

export type FigmaBrandbook = {
  tokens: Record<string, unknown>;
  rules?: { grid_columns: number; grid_gutter: number };
  source: { format: 'fig'; file_name: string; sha256: string; parser: string; warnings: string[]; observed: unknown };
};

function role(name: string, allowed: string[]) {
  const parts = name.toLowerCase().split(/[\/.:\s-]+/);
  return allowed.find(item => parts.includes(item));
}

/** Only explicit node labels assign token roles; unknown roles stay unclassified. */
export function extractFigTokens(doc: Pick<FigDocument, 'nodes'>, fileName: string, sha256: string): FigmaBrandbook {
  if (!Array.isArray(doc.nodes) || doc.nodes.length > 100_000) throw new Error('В .fig слишком много объектов (предел 100 000).');
  const colors: Array<{ hex: string; role: string }> = [];
  const fonts: Array<{ family: string; role: string }> = [];
  const sizes: Array<{ size_pt: number; role: string }> = [];
  const observedFonts: Array<{ node: string; family?: string; size_px?: number }> = [];
  const grids: Array<{ node: string; columns: number; gutter: number; guides: number[] }> = [];
  const warnings = ['Роли токенов взяты только из явных названий объектов. Размеры шрифта переведены из px в pt (× 0,75).'];
  for (const node of doc.nodes) {
    if (node.visible === false || node.phase === 'REMOVED' || node.opacity === 0) continue;
    const name = typeof node.name === 'string' ? node.name : '';
    for (const paint of node.fillPaints ?? []) {
      const c = paint.color;
      if (paint.type !== 'SOLID' || paint.visible === false || (paint.opacity ?? 1) !== 1 || !c || c.a !== 1 ||
          ![c.r, c.g, c.b].every(v => Number.isFinite(v) && v >= 0 && v <= 1)) continue;
      const hex = [c.r, c.g, c.b].map(v => Math.round(v * 255).toString(16).padStart(2, '0')).join('').toUpperCase();
      const item = { hex, role: role(name, ['background', 'surface', 'text_muted', 'text', 'accent_alt', 'accent']) ?? 'other' };
      if (!colors.some(c => c.hex === hex && c.role === item.role)) colors.push(item);
    }
    if (node.type === 'TEXT') {
      const family = node.fontName?.family;
      const size = node.fontSize;
      if (family || size) observedFonts.push({ node: name, family, size_px: size });
      const fontRole = role(name, ['heading', 'body', 'mono']) ?? (role(name, ['title', 'display']) ? 'heading' : 'other');
      if (typeof family === 'string' && family.trim() && family.length <= 200 && !fonts.some(f => f.family === family && f.role === fontRole))
        fonts.push({ family, role: fontRole });
      const sizeRole = role(name, ['display', 'title', 'heading', 'body', 'caption']);
      if (sizeRole && typeof size === 'number' && Number.isFinite(size) && size > 0 && size <= 400 &&
          !sizes.some(s => s.size_pt === size * 0.75 && s.role === sizeRole)) sizes.push({ size_pt: size * 0.75, role: sizeRole });
    }
    if (!Array.isArray(node.layoutGrids)) continue;
    for (const grid of node.layoutGrids) {
      const width = node.size?.x;
      if (grid.visible === false || grid.pattern !== 'STRIPES' || grid.type !== 'STRETCH' || grid.axis !== 'X' ||
          typeof width !== 'number' || !Number.isFinite(width) || width <= 0 ||
          !Number.isInteger(grid.numSections) || grid.numSections < 1 || grid.numSections > 24 ||
          !Number.isFinite(grid.offset) || grid.offset < 0 || !Number.isFinite(grid.gutterSize) || grid.gutterSize < 0) continue;
      const count = grid.numSections;
      const cell = (width - 2 * grid.offset - (count - 1) * grid.gutterSize) / count;
      if (cell <= 0) continue;
      const guides = Array.from({ length: count }, (_, i) => (grid.offset + i * (cell + grid.gutterSize)) / width);
      guides.push((width - grid.offset) / width);
      grids.push({ node: name, columns: count, gutter: grid.gutterSize / width, guides });
    }
  }
  if (colors.length > 256 || fonts.length > 64 || sizes.length > 64 || observedFonts.length > 1000 || grids.length > 128)
    throw new Error('В .fig слишком много разных стилей. Экспортируйте отдельную страницу брендбука.');
  if (!colors.length && !fonts.length && !sizes.length && !grids.length)
    throw new Error('В .fig не найдены поддерживаемые непрозрачные заливки, шрифты или явные колоночные сетки.');
  const tokens: Record<string, unknown> = {};
  if (colors.length) tokens.colors = colors;
  if (fonts.length) tokens.fonts = fonts;
  if (sizes.length) tokens.type_scale = sizes;
  const uniqueGrids = new Set(grids.map(g => JSON.stringify([g.columns, g.gutter, g.guides])));
  let rules: FigmaBrandbook['rules'];
  if (uniqueGrids.size === 1) {
    tokens.guides_x = grids[0].guides;
    rules = { grid_columns: grids[0].columns, grid_gutter: grids[0].gutter };
  } else if (uniqueGrids.size > 1) warnings.push('В документе разные колоночные сетки; единая сетка не выбрана.');
  if (!sizes.length && observedFonts.length) warnings.push('Кегли без явной роли сохранены в происхождении; шкала размеров не угадана.');
  warnings.push('Градиенты, прозрачные заливки, неколоночные сетки и неразрешённые переменные не превращаются в токены.');
  return { tokens, ...(rules ? { rules } : {}), source: {
    format: 'fig', file_name: fileName, sha256, parser: 'kiwi-schema@0.5.0 interpreted decoder (VoiceDeck)', warnings,
    observed: { fonts: observedFonts, column_grids: grids, node_count: doc.nodes.length },
  } };
}
