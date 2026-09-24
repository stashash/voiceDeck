import { describe, it, expect } from 'vitest';
import { agentDisplayName, agentOptionSub } from './agentName';

describe('agentDisplayName', () => {
  it('CLI-агент отдаёт имя сервиса как есть', () => {
    expect(agentDisplayName({ kind: 'cli', name: 'Claude Code', model: null, id: 'cli:claude' })).toBe('Claude Code');
  });
  it('qwen/qwen3.8-27b становится «Qwen3.8 27B в LM Studio»', () => {
    expect(agentDisplayName({ kind: 'local', name: 'qwen/qwen3.8-27b', model: 'qwen/qwen3.8-27b', id: 'local:qwen/qwen3.8-27b' }))
      .toBe('Qwen3.8 27B в LM Studio');
  });
  it('google/gemma-4-26b-a4b становится «Gemma 4 26B в LM Studio» (a4b — активные параметры, убирается)', () => {
    expect(agentDisplayName({ kind: 'local', name: 'google/gemma-4-26b-a4b', model: 'google/gemma-4-26b-a4b', id: 'local:google/gemma-4-26b-a4b' }))
      .toBe('Gemma 4 26B в LM Studio');
  });
  it('без model берёт id без префикса local:', () => {
    expect(agentDisplayName({ kind: 'local', name: 'x', model: null, id: 'local:qwen/qwen3.8-27b' }))
      .toBe('Qwen3.8 27B в LM Studio');
  });
});

describe('agentOptionSub', () => {
  it('у CLI отдаёт detail сервиса как есть', () => {
    expect(agentOptionSub({ kind: 'cli', detail: '2.1.270, найден в PATH', found: true })).toBe('2.1.270, найден в PATH');
  });
  it('у локальной модели не показывает внутренний адрес docker, только «LM Studio, загружена»', () => {
    expect(agentOptionSub({ kind: 'local', detail: 'http://host.docker.internal:1234/v1', found: true })).toBe('LM Studio, загружена');
  });
  it('у ненайденной локальной модели без «загружена»', () => {
    expect(agentOptionSub({ kind: 'local', detail: 'http://host.docker.internal:1234/v1', found: false })).toBe('LM Studio');
  });
});
