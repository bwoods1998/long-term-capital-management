// Funded Jev judgments (choice, noul and score). No trading or release authority is attached to answers.
// https://docs.typesafe.ai/models and /api, checked September 20, 2026.
import { parseUsdMicro, formatUsdMicro } from './money.mjs';

export const MODEL = 'jev-1.13.0';
export const ENDPOINT = 'https://api.typesafe.ai/v1/systemone';
export const MAX_BODY_BYTES = 64 * 1024;
// Published 64k total input limit at $0.042/M, free output: < $0.003 per request.
// Reserve a full cent, including ambiguous failures; never infer a free call from HTTP status.
export const RESERVATION_MICRO = 10000n;
export const MAX_CALLS = 500000;
export const capMicro = env => parseUsdMicro(env.TYPESAFE_PILOT_USD, 0n);
export const money = formatUsdMicro;

const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
const text = x => typeof x === 'string' && x.trim().length > 0;
const keysOnly = (x, keys) => Object.keys(x).every(k => keys.includes(k));
const ident = x => typeof x === 'string' && /^[a-zA-Z0-9_-]{1,64}$/.test(x);

export function admit(body) {
  if (!object(body) || !keysOnly(body, ['model', 'state', 'questions']) || body.model !== MODEL
      || !(text(body.state) || object(body.state) || Array.isArray(body.state)) || !object(body.questions)) {
    return 'Supply the pinned model, inline text/JSON state and typed questions only.';
  }
  const questions = Object.entries(body.questions);
  if (!questions.length || questions.length > 16) return 'Supply 1 to 16 questions.';
  for (const [name, q] of questions) {
    if (!ident(name) || !object(q) || !keysOnly(q, ['type', 'instructions', 'criteria']) || !text(q.instructions)) {
      return 'Each question needs a simple identifier and explicit text instructions.';
    }
    if (q.type === 'choice') {
      if (!object(q.criteria)) return 'A choice needs explicit options.';
      const options = Object.entries(q.criteria);
      if (options.length < 2 || options.length > 32 || options.some(([k, v]) => !ident(k) || !text(v))) {
        return 'A choice needs 2 to 32 named options with text descriptions.';
      }
    } else if (q.type === 'noul') {
      if (q.criteria !== undefined && (!object(q.criteria) || !keysOnly(q.criteria, ['true', 'false'])
          || Object.values(q.criteria).some(v => !text(v)))) return 'Noul criteria must describe true/false.';
    } else if (q.type === 'score') {
      // A rubric: 2 to 10 ordered levels, lowest first (docs.typesafe.ai/api, checked Sept 25, 2026).
      if (!Array.isArray(q.criteria) || q.criteria.length < 2 || q.criteria.length > 10 || !q.criteria.every(text)) {
        return 'A score needs 2 to 10 ordered level descriptions.';
      }
    } else return 'Jev questions are choice, noul or score.';
  }
  return null;
}

export function actualCost(usage) {
  if (!object(usage) || !Number.isSafeInteger(usage.input_tokens) || usage.input_tokens < 0) return null;
  // Exact microdollars: $0.042/M tokens = 42/1000 microdollars per input token.
  return (BigInt(usage.input_tokens) * 42n + 999n) / 1000n;
}

/**
 * Why a response is not what was asked, in the gateway's own words (never the provider's text):
 * `top` for the envelope, `questions` for each answer that fails its type's rules. Sept 25, 2026:
 * 92 of 535 market-map requests (8% of 2-question batches, 41% of 16-question ones) were refused
 * whole for one bad answer, although every call was billed, so the problems are named per question.
 */
export function answerProblems(body, response) {
  const questions = object(body?.questions) ? body.questions : {};
  if (!object(response) || response.model !== MODEL || !object(response.answers)) {
    return { top: 'the response is not a typed answer from the pinned model', questions: {} };
  }
  const extra = Object.keys(response.answers).filter(name => !Object.hasOwn(questions, name));
  if (extra.length) return { top: `the response answers ${extra.length} question(s) that were not asked`, questions: {} };
  const problems = {};
  for (const [name, q] of Object.entries(questions)) {
    const problem = answerProblem(q, response.answers[name]);
    if (problem) problems[name] = problem;
  }
  return { top: null, questions: problems };
}

const probability = n => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1;

function answerProblem(q, a) {
  if (a === undefined) return 'no answer';
  if (!object(a) || a.type !== q.type) return `not a ${q.type} answer`;
  if (q.type === 'noul') return probability(a.noul) ? null : 'noul is not a probability';
  if (q.type === 'score') {
    // Levels are keyed "0".."n-1"; the score is the probability-weighted level, so it lies in
    // [0, n-1] and equals the sum of index x probability (a small rounding allowance either way).
    const levels = q.criteria.map((_, i) => String(i));
    if (!probability(a.confidence)) return 'confidence is not a probability';
    if (typeof a.score !== 'number' || !Number.isFinite(a.score)) return 'score is not a number';
    if (!object(a.probabilities)) return 'no probabilities';
    if (Object.keys(a.probabilities).length !== levels.length || !levels.every(n => probability(a.probabilities[n]))) {
      return 'probabilities do not match the levels';
    }
    if (Math.abs(levels.reduce((sum, n) => sum + a.probabilities[n], 0) - 1) > 0.001) return 'probabilities do not sum to 1';
    const expected = levels.reduce((sum, n) => sum + Number(n) * a.probabilities[n], 0);
    if (a.score < -0.01 || a.score > levels.length - 1 + 0.01) return 'score is outside the levels';
    return Math.abs(a.score - expected) <= 0.02 ? null : 'score is not the probability-weighted level';
  }
  if (typeof a.choice !== 'string' || !Object.hasOwn(q.criteria, a.choice)) return 'the choice is not one of the options';
  if (!probability(a.confidence)) return 'confidence is not a probability';
  if (!object(a.probabilities)) return 'no probabilities';
  const names = Object.keys(q.criteria);
  if (Object.keys(a.probabilities).length !== names.length || !names.every(n => probability(a.probabilities[n]))) {
    return 'probabilities do not match the options';
  }
  return Math.abs(names.reduce((sum, n) => sum + a.probabilities[n], 0) - 1) <= 0.001 ? null : 'probabilities do not sum to 1';
}

export function validAnswers(body, response) {
  const problems = answerProblems(body, response);
  return !problems.top && !Object.keys(problems.questions).length;
}

/** The answers that passed, for a caller that asked for partial answers (`X-LTCM-Partial: 1`). */
export function partial(response, rejected) {
  const answers = Object.fromEntries(Object.entries(response.answers).filter(([name]) => !Object.hasOwn(rejected, name)));
  return { ...response, answers, rejected };
}
