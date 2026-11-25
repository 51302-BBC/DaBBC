import assert from 'node:assert/strict';
import test from 'node:test';
import { monthDates, taipeiDate } from './dates.js';

test('month starts on Monday and supplies complete weeks', () => {
  const days = monthDates(2026, 11);
  assert.equal(days[0], '2026-10-26');
  assert.equal(days[6], '2026-11-01');
  assert.equal(days.at(-1), '2026-12-06');
  assert.equal(days.length % 7, 0);
});

test('Taipei attendance day changes at local midnight', () => {
  assert.equal(taipeiDate(new Date('2026-11-24T16:01:00Z')), '2026-11-25');
});
