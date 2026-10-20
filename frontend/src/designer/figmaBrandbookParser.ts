import { Inflate, unzipSync } from 'fflate';
import { Decompress } from 'fzstd';
import { ByteBuffer, decodeBinarySchema } from 'kiwi-schema';
import type { Definition, Field, Schema } from 'kiwi-schema';
import type { FigDocument } from 'openfig-core';

const MAX_EXPANDED_BYTES = 32 * 1024 * 1024;

function expand(bytes: Uint8Array, zstd: boolean, limit: number): Uint8Array {
  const chunks: Uint8Array[] = [];
  let total = 0;
  const accept = (chunk: Uint8Array) => {
    total += chunk.length;
    if (total > limit) throw new Error('Распакованные данные .fig превышают допустимый размер.');
    chunks.push(chunk);
  };
  const decoder = zstd ? new Decompress(accept) : new Inflate(accept);
  decoder.push(bytes, true);
  const output = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { output.set(chunk, offset); offset += chunk.length; }
  return output;
}

/** Interpret Kiwi wire fields as data. No schema name or value becomes JavaScript. */
export function interpretKiwiMessage(schema: Schema, bytes: Uint8Array): Record<string, unknown> {
  if (schema.definitions.length > 10_000) throw new Error('Слишком большая схема .fig.');
  const definitions = new Map<string, Definition>();
  const fields = new Map<string, Map<number, Field>>();
  let fieldCount = 0;
  for (const definition of schema.definitions) {
    if (definitions.has(definition.name) || !['ENUM', 'STRUCT', 'MESSAGE'].includes(definition.kind)) throw new Error('Некорректная схема .fig.');
    definitions.set(definition.name, definition);
    const lookup = new Map<number, Field>();
    for (const field of definition.fields) {
      if (++fieldCount > 100_000 || lookup.has(field.value)) throw new Error('Некорректные поля схемы .fig.');
      lookup.set(field.value, field);
    }
    fields.set(definition.name, lookup);
  }
  const bb = new ByteBuffer(bytes);
  let operations = 0;
  function read(type: string, depth: number): unknown {
    if (++operations > 2_000_000 || depth > 64) throw new Error('Слишком сложная структура .fig.');
    switch (type) {
      case 'bool': return !!bb.readByte();
      case 'byte': return bb.readByte();
      case 'int': return bb.readVarInt();
      case 'uint': return bb.readVarUint();
      case 'float': return bb.readVarFloat();
      case 'string': return bb.readString();
      case 'int64': return bb.readVarInt64();
      case 'uint64': return bb.readVarUint64();
    }
    const definition = definitions.get(type);
    if (!definition) throw new Error('Неизвестный тип схемы .fig.');
    if (definition.kind === 'ENUM') {
      const field = fields.get(type)!.get(bb.readVarUint());
      if (!field) throw new Error('Неизвестное значение перечисления .fig.');
      return field.name;
    }
    const result: Record<string, unknown> = Object.create(null);
    function readField(field: Field) {
      if (!field.type) throw new Error('Некорректный тип поля .fig.');
      let value: unknown;
      if (field.isArray && field.type === 'byte') value = bb.readByteArray();
      else if (field.isArray) {
        const count = bb.readVarUint();
        if (count > 200_000) throw new Error('Слишком большой массив .fig.');
        const array: unknown[] = [];
        for (let i = 0; i < count; i++) array.push(read(field.type, depth + 1));
        value = array;
      } else value = read(field.type, depth + 1);
      if (!field.isDeprecated) result[field.name] = value;
    }
    if (definition.kind === 'STRUCT') for (const field of definition.fields) readField(field);
    else {
      while (true) {
        if (++operations > 2_000_000) throw new Error('Слишком сложная структура .fig.');
        const tag = bb.readVarUint();
        if (!tag) break;
        const field = fields.get(type)!.get(tag);
        if (!field) throw new Error('Неизвестное поле сообщения .fig.');
        readField(field);
      }
    }
    return result;
  }
  return read('Message', 0) as Record<string, unknown>;
}

/** Decode only the canvas needed for tokens; images and executable schema compilation are absent. */
export function parseFigForBrandbook(bytes: Uint8Array): Pick<FigDocument, 'nodes'> {
  if (bytes.length > 20 * 1024 * 1024) throw new Error('Файл .fig больше 20 МБ.');
  const entries = unzipSync(bytes, { filter: entry => {
    if (!/(?:^|\/)canvas\.fig$/.test(entry.name)) return false;
    if (entry.originalSize > MAX_EXPANDED_BYTES) throw new Error('Canvas .fig больше 32 МБ.');
    return true;
  } });
  const canvases = Object.values(entries);
  if (canvases.length !== 1) throw new Error('В .fig нужен один canvas.fig.');
  const canvas = canvases[0];
  if (canvas.length < 12 || new TextDecoder().decode(canvas.subarray(0, 8)) !== 'fig-kiwi') throw new Error('Неподдерживаемый формат canvas.fig.');
  const view = new DataView(canvas.buffer, canvas.byteOffset, canvas.byteLength);
  const chunks: Uint8Array[] = [];
  for (let offset = 12; offset < canvas.length;) {
    if (offset + 4 > canvas.length) throw new Error('Обрезанный блок .fig.');
    const count = view.getUint32(offset, true);
    offset += 4;
    if (offset + count > canvas.length) throw new Error('Обрезанный блок .fig.');
    chunks.push(canvas.subarray(offset, offset + count));
    offset += count;
    if (chunks.length > 128) throw new Error('Слишком много блоков .fig.');
  }
  if (chunks.length < 2) throw new Error('В .fig отсутствуют схема или данные.');
  const schema = decodeBinarySchema(expand(chunks[0], false, 2 * 1024 * 1024));
  const messageBytes = chunks[1];
  const zstd = messageBytes[0] === 0x28 && messageBytes[1] === 0xb5 && messageBytes[2] === 0x2f && messageBytes[3] === 0xfd;
  const message = interpretKiwiMessage(schema, expand(messageBytes, zstd, MAX_EXPANDED_BYTES));
  if (!Array.isArray(message.nodeChanges)) throw new Error('В .fig отсутствуют объекты.');
  return { nodes: message.nodeChanges as FigDocument['nodes'] };
}
