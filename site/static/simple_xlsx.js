(function () {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder('utf-8');

  function bytes(text) {
    return encoder.encode(String(text));
  }

  function text(data) {
    return decoder.decode(data);
  }

  function xmlEscape(value) {
    return String(value == null ? '' : value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&apos;');
  }

  function colName(index) {
    let n = index;
    let name = '';
    while (n > 0) {
      const mod = (n - 1) % 26;
      name = String.fromCharCode(65 + mod) + name;
      n = Math.floor((n - 1) / 26);
    }
    return name;
  }

  function colIndex(ref) {
    const letters = String(ref || '').replace(/[^A-Z]/gi, '').toUpperCase();
    let value = 0;
    for (const ch of letters) value = value * 26 + ch.charCodeAt(0) - 64;
    return value;
  }

  function isNumericCell(value) {
    return typeof value === 'number' && Number.isFinite(value);
  }

  function cellXml(value, rowIdx, colIdx) {
    if (value == null || value === '') return '';
    const ref = `${colName(colIdx)}${rowIdx}`;
    if (isNumericCell(value)) return `<c r="${ref}"><v>${value}</v></c>`;
    return `<c r="${ref}" t="inlineStr"><is><t>${xmlEscape(value)}</t></is></c>`;
  }

  function worksheetXml(sheet) {
    const headers = sheet.headers || Object.keys((sheet.rows && sheet.rows[0]) || {});
    const rows = [headers].concat((sheet.rows || []).map((row) => headers.map((header) => row[header])));
    const sheetRows = rows.map((row, rIdx) => {
      const rowNumber = rIdx + 1;
      const cells = row.map((value, cIdx) => cellXml(value, rowNumber, cIdx + 1)).join('');
      return `<row r="${rowNumber}">${cells}</row>`;
    }).join('');
    const cols = headers.map((header, idx) => {
      const max = Math.max(String(header).length, ...((sheet.rows || []).map((row) => String(row[header] == null ? '' : row[header]).length)));
      const width = Math.max(10, Math.min(24, max + 3));
      return `<col min="${idx + 1}" max="${idx + 1}" width="${width}" customWidth="1"/>`;
    }).join('');
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cols>${cols}</cols>
  <sheetData>${sheetRows}</sheetData>
</worksheet>`;
  }

  function workbookXml(sheets) {
    const sheetNodes = sheets.map((sheet, idx) => (
      `<sheet name="${xmlEscape(sheet.name)}" sheetId="${idx + 1}" r:id="rId${idx + 1}"/>`
    )).join('');
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>${sheetNodes}</sheets>
</workbook>`;
  }

  function workbookRelsXml(sheets) {
    const rels = sheets.map((sheet, idx) => (
      `<Relationship Id="rId${idx + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${idx + 1}.xml"/>`
    )).join('');
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  ${rels}
  <Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`;
  }

  function contentTypesXml(sheets) {
    const overrides = sheets.map((sheet, idx) => (
      `<Override PartName="/xl/worksheets/sheet${idx + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`
    )).join('');
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  ${overrides}
</Types>`;
  }

  function rootRelsXml() {
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`;
  }

  function stylesXml() {
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>`;
  }

  let crcTable = null;
  function crc32(data) {
    if (!crcTable) {
      crcTable = new Uint32Array(256);
      for (let i = 0; i < 256; i += 1) {
        let c = i;
        for (let j = 0; j < 8; j += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        crcTable[i] = c >>> 0;
      }
    }
    let crc = 0xffffffff;
    for (let i = 0; i < data.length; i += 1) crc = crcTable[(crc ^ data[i]) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }

  function dosTimeParts(date) {
    const year = Math.max(1980, date.getFullYear());
    return {
      time: (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2),
      date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
    };
  }

  function concat(parts) {
    const total = parts.reduce((sum, part) => sum + part.length, 0);
    const out = new Uint8Array(total);
    let offset = 0;
    parts.forEach((part) => {
      out.set(part, offset);
      offset += part.length;
    });
    return out;
  }

  function zip(files) {
    const now = dosTimeParts(new Date());
    const localParts = [];
    const centralParts = [];
    let offset = 0;
    files.forEach((file) => {
      const nameBytes = bytes(file.name);
      const data = typeof file.data === 'string' ? bytes(file.data) : file.data;
      const crc = crc32(data);
      const local = new Uint8Array(30 + nameBytes.length);
      const localView = new DataView(local.buffer);
      localView.setUint32(0, 0x04034b50, true);
      localView.setUint16(4, 20, true);
      localView.setUint16(6, 0x0800, true);
      localView.setUint16(8, 0, true);
      localView.setUint16(10, now.time, true);
      localView.setUint16(12, now.date, true);
      localView.setUint32(14, crc, true);
      localView.setUint32(18, data.length, true);
      localView.setUint32(22, data.length, true);
      localView.setUint16(26, nameBytes.length, true);
      local.set(nameBytes, 30);

      const central = new Uint8Array(46 + nameBytes.length);
      const centralView = new DataView(central.buffer);
      centralView.setUint32(0, 0x02014b50, true);
      centralView.setUint16(4, 20, true);
      centralView.setUint16(6, 20, true);
      centralView.setUint16(8, 0x0800, true);
      centralView.setUint16(10, 0, true);
      centralView.setUint16(12, now.time, true);
      centralView.setUint16(14, now.date, true);
      centralView.setUint32(16, crc, true);
      centralView.setUint32(20, data.length, true);
      centralView.setUint32(24, data.length, true);
      centralView.setUint16(28, nameBytes.length, true);
      centralView.setUint32(42, offset, true);
      central.set(nameBytes, 46);

      localParts.push(local, data);
      centralParts.push(central);
      offset += local.length + data.length;
    });

    const centralDir = concat(centralParts);
    const end = new Uint8Array(22);
    const endView = new DataView(end.buffer);
    endView.setUint32(0, 0x06054b50, true);
    endView.setUint16(8, files.length, true);
    endView.setUint16(10, files.length, true);
    endView.setUint32(12, centralDir.length, true);
    endView.setUint32(16, offset, true);
    return concat(localParts.concat([centralDir, end]));
  }

  function writeWorkbook(sheets) {
    const files = [
      { name: '[Content_Types].xml', data: contentTypesXml(sheets) },
      { name: '_rels/.rels', data: rootRelsXml() },
      { name: 'xl/workbook.xml', data: workbookXml(sheets) },
      { name: 'xl/_rels/workbook.xml.rels', data: workbookRelsXml(sheets) },
      { name: 'xl/styles.xml', data: stylesXml() },
    ];
    sheets.forEach((sheet, idx) => {
      files.push({ name: `xl/worksheets/sheet${idx + 1}.xml`, data: worksheetXml(sheet) });
    });
    return new Blob([zip(files)], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
  }

  async function inflate(data, method) {
    if (method === 0) return data;
    if (method !== 8) throw new Error(`不支援的 XLSX 壓縮格式：${method}`);
    if (!window.DecompressionStream) throw new Error('目前瀏覽器不支援解壓縮一般 Excel XLSX');
    try {
      const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
      return new Uint8Array(await new Response(stream).arrayBuffer());
    } catch (err) {
      const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate'));
      return new Uint8Array(await new Response(stream).arrayBuffer());
    }
  }

  async function unzip(buffer) {
    const data = new Uint8Array(buffer);
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    let eocd = -1;
    for (let i = data.length - 22; i >= Math.max(0, data.length - 66000); i -= 1) {
      if (view.getUint32(i, true) === 0x06054b50) {
        eocd = i;
        break;
      }
    }
    if (eocd < 0) throw new Error('找不到 XLSX 壓縮目錄');
    const count = view.getUint16(eocd + 10, true);
    let ptr = view.getUint32(eocd + 16, true);
    const files = new Map();
    for (let i = 0; i < count; i += 1) {
      if (view.getUint32(ptr, true) !== 0x02014b50) throw new Error('XLSX 壓縮目錄格式錯誤');
      const method = view.getUint16(ptr + 10, true);
      const compressedSize = view.getUint32(ptr + 20, true);
      const nameLen = view.getUint16(ptr + 28, true);
      const extraLen = view.getUint16(ptr + 30, true);
      const commentLen = view.getUint16(ptr + 32, true);
      const localOffset = view.getUint32(ptr + 42, true);
      const name = text(data.slice(ptr + 46, ptr + 46 + nameLen));
      const localNameLen = view.getUint16(localOffset + 26, true);
      const localExtraLen = view.getUint16(localOffset + 28, true);
      const start = localOffset + 30 + localNameLen + localExtraLen;
      const raw = data.slice(start, start + compressedSize);
      files.set(name, await inflate(raw, method));
      ptr += 46 + nameLen + extraLen + commentLen;
    }
    return files;
  }

  function parseXml(xml) {
    const doc = new DOMParser().parseFromString(xml, 'application/xml');
    if (doc.getElementsByTagName('parsererror').length) throw new Error('XLSX XML 解析失敗');
    return doc;
  }

  function byLocal(root, name) {
    return Array.from(root.getElementsByTagName('*')).filter((node) => node.localName === name);
  }

  function relMap(xml) {
    const doc = parseXml(xml);
    const map = {};
    byLocal(doc, 'Relationship').forEach((rel) => {
      map[rel.getAttribute('Id')] = rel.getAttribute('Target');
    });
    return map;
  }

  function resolvePath(base, target) {
    if (target.startsWith('/')) return target.slice(1);
    const parts = base.split('/');
    parts.pop();
    target.split('/').forEach((part) => {
      if (!part || part === '.') return;
      if (part === '..') parts.pop();
      else parts.push(part);
    });
    return parts.join('/');
  }

  function parseSharedStrings(xml) {
    if (!xml) return [];
    const doc = parseXml(xml);
    return byLocal(doc, 'si').map((node) => byLocal(node, 't').map((tNode) => tNode.textContent || '').join(''));
  }

  function readCell(cell, sharedStrings) {
    const type = cell.getAttribute('t');
    if (type === 'inlineStr') return byLocal(cell, 't').map((node) => node.textContent || '').join('');
    const vNode = byLocal(cell, 'v')[0];
    const raw = vNode ? vNode.textContent || '' : '';
    if (type === 's') return sharedStrings[Number(raw)] || '';
    if (type === 'b') return raw === '1' ? 'TRUE' : 'FALSE';
    if (type === 'str') return raw;
    if (raw === '') return '';
    const n = Number(raw);
    return Number.isFinite(n) ? n : raw;
  }

  function parseSheet(xml, sharedStrings) {
    const doc = parseXml(xml);
    const rows = byLocal(doc, 'row').map((rowNode) => {
      const values = [];
      byLocal(rowNode, 'c').forEach((cell) => {
        values[colIndex(cell.getAttribute('r')) - 1] = readCell(cell, sharedStrings);
      });
      return values.map((value) => value == null ? '' : value);
    }).filter((row) => row.some((value) => String(value).trim() !== ''));
    const headers = (rows.shift() || []).map((header) => String(header).trim());
    return rows.map((row) => {
      const item = {};
      headers.forEach((header, idx) => {
        if (header) item[header] = row[idx] == null ? '' : row[idx];
      });
      return item;
    });
  }

  async function readWorkbook(buffer) {
    const files = await unzip(buffer);
    const workbookPath = 'xl/workbook.xml';
    const workbook = parseXml(text(files.get(workbookPath)));
    const rels = relMap(text(files.get('xl/_rels/workbook.xml.rels')));
    const sharedStrings = parseSharedStrings(files.has('xl/sharedStrings.xml') ? text(files.get('xl/sharedStrings.xml')) : '');
    const sheets = {};
    byLocal(workbook, 'sheet').forEach((sheet) => {
      const name = sheet.getAttribute('name') || '';
      const relId = sheet.getAttribute('r:id') || sheet.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id');
      const target = rels[relId];
      if (!name || !target) return;
      const path = resolvePath(workbookPath, target);
      if (!files.has(path)) return;
      sheets[name] = parseSheet(text(files.get(path)), sharedStrings);
    });
    return sheets;
  }

  window.StockFuturesXlsx = { writeWorkbook, readWorkbook };
}());
