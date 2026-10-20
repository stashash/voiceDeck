import { describe, expect, it } from 'vitest';
import { semanticAnalysisGoal } from './SemanticDataPlan';

describe('semantic content goal', () => {
  it('uses the full presentation brief for automatic detection', () => {
    const brief = 'Сравнить план и факт за апрель. Решить, где нужно внимание.';
    expect(semanticAnalysisGoal(brief, '')).toBe(brief);
    expect(semanticAnalysisGoal('', '')).toBe('');
  });
  it('honors a selected explicit question over contradictory wording in the brief', () => {
    expect(semanticAnalysisGoal('Показать рост', 'Показать доли структуры')).toBe('Показать доли структуры');
  });
});
