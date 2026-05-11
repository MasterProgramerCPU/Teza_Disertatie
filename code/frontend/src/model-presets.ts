import type { ModelType } from "@/types";

export const MODEL_LABELS: Record<ModelType, string> = {
  sidarth: "SIDARTH",
  sir: "SIR",
};

export const COMPARTMENT_LABELS: Record<string, string> = {
  s: "S",
  i: "I",
  d: "D",
  a: "A",
  r: "R",
  t: "T",
  h: "H",
};

export const PARAMETER_LABELS: Record<string, string> = {
  alpha: "alpha",
  beta: "beta",
  gamma: "gamma",
  delta: "delta",
  epsilon: "epsilon",
  zeta: "zeta",
  lambda: "lambda",
  eta: "eta",
  rho: "rho",
  theta: "theta",
  mu: "mu",
  kappa: "kappa",
  nu: "nu",
  xi: "xi",
  sigma: "sigma",
};

export const MODEL_PARAMETERS: Record<ModelType, Record<string, number>> = {
  sidarth: {
    alpha: 0.57,
    beta: 0.011,
    gamma: 0.456,
    delta: 0.011,
    epsilon: 0.171,
    zeta: 0.125,
    lambda: 0.034,
    eta: 0.125,
    rho: 0.034,
    theta: 0.37,
    mu: 0.017,
    kappa: 0.017,
    nu: 0.027,
    xi: 0.017,
    sigma: 0.017,
  },
  sir: {
    beta: 0.3,
    gamma: 0.0714,
  },
};

export const MODEL_PARAMETER_ORDER: Record<ModelType, string[]> = {
  sidarth: [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "zeta",
    "lambda",
    "eta",
    "rho",
    "theta",
    "mu",
    "kappa",
    "nu",
    "xi",
    "sigma",
  ],
  sir: ["beta", "gamma"],
};

export function defaultParameters(modelType: ModelType): Record<string, number> {
  return { ...MODEL_PARAMETERS[modelType] };
}
