"""Generator de seturi de date sintetice pentru stresarea sistemului.

Spre deosebire de preprocesarea OWID, acest script nu deriva date dintr-o sursa
reala, ci simuleaza inainte un model compartimental SIRS cu fortare sezoniera si
scrie traiectoria rezultata in aceeasi schema CSV:

    date, region, infected, population, recovered, susceptible

Scopul este sa produca serii arbitrar de lungi si cu dinamica controlata, pentru
benchmarking: orizonturi de zeci de mii de zile (utile mai ales runner-ului
LSTM, al carui cost de antrenare creste cu lungimea seriei) si volume mari de
inserari in baza de date. Modelul folosit este SIRS, ales pentru ca imunitatea
care se pierde (R -> S) sustine valuri recurente pe orizont lung; fortarea
sezoniera a ratei de transmitere produce valuri anuale realiste.

SIRS cu fortare sezoniera:
    beta(t) = beta0 * (1 + amp * sin(2*pi*t / period))
    dS/dt = -beta(t) * S * I / N + xi * R
    dI/dt =  beta(t) * S * I / N - gamma * I
    dR/dt =  gamma * I - xi * R

Integrarea foloseste Runge-Kutta de ordin 4 cu pas zilnic. Conservarea
S + I + R = N este impusa exact dupa rotunjire (susceptibilii se recalculeaza din
bilant), astfel incat fisierul sa treaca validarea din :mod:`epi_common` si din
API.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

import epi_common as epi

logger = logging.getLogger("generate_synthetic")

BASE_DATE = pd.Timestamp("2000-01-01")


@dataclass(frozen=True)
class Profile:
    """Un regim dinamic: ratele modelului SIRS si fortarea sezoniera."""
    beta0: float       # rata de transmitere de baza
    gamma: float       # rata de recuperare (1 / durata infectioasa)
    xi: float          # rata de pierdere a imunitatii (1 / durata imunitatii)
    amp: float         # amplitudinea fortarii sezoniere (0..1)
    period: float      # perioada sezoniera, in zile
    region: str        # cod de regiune (max 10 caractere, vezi schema BD)

    @property
    def r0(self) -> float:
        return self.beta0 / self.gamma


PROFILES: dict[str, Profile] = {
    # valuri anuale recurente, R0 moderat -- regimul implicit
    "multiwave": Profile(beta0=0.18, gamma=0.10, xi=1 / 180, amp=0.45, period=365.0, region="SYN-MW"),
    # valuri ascutite si dese: R0 mare, infectie scurta, imunitate scurta
    "sharp":     Profile(beta0=0.55, gamma=0.20, xi=1 / 120, amp=0.55, period=240.0, region="SYN-SH"),
    # valuri lente si largi: R0 aproape de prag, infectie lunga
    "slow":      Profile(beta0=0.075, gamma=0.05, xi=1 / 365, amp=0.30, period=730.0, region="SYN-SL"),
}


def seasonal_beta(profile: Profile, t: float) -> float:
    return profile.beta0 * (1.0 + profile.amp * np.sin(2.0 * np.pi * t / profile.period))


def sirs_rhs(state: np.ndarray, t: float, profile: Profile, n: float) -> np.ndarray:
    s, i, r = state
    beta = seasonal_beta(profile, t)
    new_inf = beta * s * i / n
    waning = profile.xi * r
    recov = profile.gamma * i
    return np.array([
        -new_inf + waning,
        new_inf - recov,
        recov - waning,
    ])


def simulate(profile: Profile, days: int, population: float, i0: float) -> np.ndarray:
    """Integreaza modelul SIRS cu RK4, pas zilnic. Returneaza matricea (days+1, 3)."""
    state = np.array([population - i0, i0, 0.0], dtype=float)
    traj = np.empty((days + 1, 3), dtype=float)
    traj[0] = state
    for k in range(days):
        t = float(k)
        k1 = sirs_rhs(state, t, profile, population)
        k2 = sirs_rhs(state + 0.5 * k1, t + 0.5, profile, population)
        k3 = sirs_rhs(state + 0.5 * k2, t + 0.5, profile, population)
        k4 = sirs_rhs(state + k3, t + 1.0, profile, population)
        state = state + (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0
        state = np.clip(state, 0.0, population)
        traj[k + 1] = state
    return traj


def to_dataframe(traj: np.ndarray, region: str, population: int,
                 noise: float, rng: np.random.Generator) -> pd.DataFrame:
    """Construieste schema CSV comuna, cu conservare exacta dupa rotunjire."""
    infected = traj[:, 1].copy()
    if noise > 0:
        # zgomot multiplicativ lognormal pe seria observata de infectati
        infected *= rng.lognormal(mean=0.0, sigma=noise, size=infected.shape)

    infected = np.round(np.clip(infected, 0.0, population)).astype("int64")
    recovered = np.round(np.clip(traj[:, 2], 0.0, population)).astype("int64")
    # I + R nu poate depasi N; susceptibilii inchid bilantul exact
    overflow = np.maximum(infected + recovered - population, 0)
    recovered = recovered - np.minimum(recovered, overflow)
    susceptible = population - infected - recovered

    days = len(infected)
    dates = pd.date_range(BASE_DATE, periods=days, freq="D")
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "region": region,
        "infected": infected,
        "population": population,
        "recovered": recovered,
        "susceptible": susceptible,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generator de seturi sintetice de stres.")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="multiwave",
                        help="regimul dinamic (implicit: multiwave)")
    parser.add_argument("--days", type=int, default=20000,
                        help="lungimea seriei in zile (implicit: 20000)")
    parser.add_argument("--population", type=int, default=50_000_000,
                        help="populatia totala N (implicit: 50.000.000)")
    parser.add_argument("--i0", type=float, default=100.0,
                        help="numarul initial de infectati (implicit: 100)")
    parser.add_argument("--noise", type=float, default=0.0,
                        help="sigma zgomotului lognormal de raportare pe infectati "
                             "(0 = serie curata, implicit)")
    parser.add_argument("--region", default=None,
                        help="codul regiunii, max 10 caractere (implicit: cel al profilului)")
    parser.add_argument("--slug", default=None,
                        help="numele fisierului de iesire (implicit: synthetic_<profile>)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    if args.days < 1:
        logger.error("--days trebuie sa fie >= 1")
        return 2
    if args.population < 1 or args.i0 < 0 or args.i0 > args.population:
        logger.error("populatie sau i0 invalid")
        return 2

    profile = PROFILES[args.profile]
    region = args.region or profile.region
    if len(region) > 10:
        logger.error("codul regiunii '%s' depaseste 10 caractere (limita schemei BD)", region)
        return 2
    slug = args.slug or f"synthetic_{args.profile}"
    rng = np.random.default_rng(args.seed)

    logger.info("profil %s: R0 baza = %.2f, gamma = %.4f, xi = %.5f",
                args.profile, profile.r0, profile.gamma, profile.xi)
    logger.info("simulez %d zile, N = %d ...", args.days, args.population)

    traj = simulate(profile, args.days, float(args.population), args.i0)
    df = to_dataframe(traj, region, args.population, args.noise, rng)
    epi.validate(df, slug)

    out_path = epi.write_processed(df, slug)
    logger.info(
        "%d randuri -> %s  (I maxim = %d, I mediu = %d)",
        len(df), out_path.relative_to(epi.REPO_ROOT),
        df["infected"].max(), int(df["infected"].mean()),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
