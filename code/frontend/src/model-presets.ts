import type { ModelType } from "@/types";

export const MODEL_LABELS: Record<ModelType, string> = {
  sidarthe: "SIDARTHE",
  sir: "SIR",
  sis: "SIS",
  seir: "SEIR",
  sirs: "SIRS",
  lstm: "LSTM",
};

export const MODEL_OPTIONS = Object.entries(MODEL_LABELS).map(([value, label]) => ({
  value: value as ModelType,
  label,
}));

export const COMPARTMENT_LABELS: Record<string, string> = {
  s: "S",
  e: "E",
  i: "I",
  d: "D",
  a: "A",
  r: "R",
  t: "T",
  h: "H",
  observed: "observat",
  fitted: "fit LSTM",
  predicted: "predicție",
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
  tau: "tau",
  lookback: "lookback",
  hidden_size: "hidden size",
  epochs: "epoci",
  learning_rate: "learning rate",
};

export const MODEL_PARAMETERS: Record<ModelType, Record<string, number>> = {
  sidarthe: {
    ...sidartheBaseParameters(),
    tau: 0.01,
  },
  sir: {
    beta: 0.3,
    gamma: 0.0714,
  },
  sis: {
    beta: 0.3,
    gamma: 0.0714,
  },
  seir: {
    beta: 0.3,
    sigma: 0.1923,
    gamma: 0.0714,
  },
  sirs: {
    beta: 0.3,
    gamma: 0.0714,
    xi: 0.0055,
  },
  lstm: {
    lookback: 14,
    hidden_size: 12,
    epochs: 150,
    learning_rate: 0.01,
  },
};

export const MODEL_PARAMETER_ORDER: Record<ModelType, string[]> = {
  sidarthe: [...sidartheBaseParameterOrder(), "tau"],
  sir: ["beta", "gamma"],
  sis: ["beta", "gamma"],
  seir: ["beta", "sigma", "gamma"],
  sirs: ["beta", "gamma", "xi"],
  lstm: ["lookback", "hidden_size", "epochs", "learning_rate"],
};

export function defaultParameters(modelType: ModelType): Record<string, number> {
  return { ...MODEL_PARAMETERS[modelType] };
}

function sidartheBaseParameters(): Record<string, number> {
  return {
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
  };
}

function sidartheBaseParameterOrder(): string[] {
  return [
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
  ];
}
