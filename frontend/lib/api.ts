const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8111';

export async function apiFetch(path: string, options?: RequestInit) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  return res.json();
}

export async function getHealth() {
  return apiFetch('/health');
}

export async function simulate(body: unknown) {
  return apiFetch('/simulate', { method: 'POST', body: JSON.stringify(body) });
}

export async function mctsRecommend(state: Record<string, unknown>, iterations = 1000, enemyModel = 'average') {
  return apiFetch('/mcts/recommend', {
    method: 'POST',
    body: JSON.stringify({ state, iterations, enemy_model: enemyModel }),
  });
}

export async function mctsPlan(state: Record<string, unknown>, steps = 6, enemyModel = 'average', iterationsPerStep = 500) {
  return apiFetch('/mcts/plan', {
    method: 'POST',
    body: JSON.stringify({ state, steps, enemy_model: enemyModel, iterations_per_step: iterationsPerStep }),
  });
}

export async function getPatches() {
  return apiFetch('/patches');
}

export async function getPatch(version: string) {
  return apiFetch(`/patches/${version}`);
}

export async function getPatchByRole(version: string, role: string) {
  return apiFetch(`/patches/${version}/role/${role}`);
}

export async function decodePatch(url?: string) {
  return apiFetch('/patches/decode', {
    method: 'POST',
    body: JSON.stringify(url ? { url } : {}),
  });
}
