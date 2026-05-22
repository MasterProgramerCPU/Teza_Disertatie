# Plan — Secțiunea „Lucrări și instrumente conexe” (related work)

## Plasare
Capitolul 1 (`docs/chapters/01_introducere.tex`), între `§sec:context`
(Context și motivație) și `§sec:obiective` (Obiectivele lucrării).

Flow narativ rezultat: **context → lucrări conexe → obiective → contribuții → structură**.

Label nou: `\section{Lucrări și instrumente conexe}\label{sec:lucrari_inrudite}`.

## Structură (5 paragrafe, pe categorii)

1. **Biblioteci de solver ODE** — fundațiile deja folosite în lucrare:
   `deSolve` (R) \cite{soetaert2010desolve}, `DifferentialEquations.jl` (Julia)
   \cite{rackauckas2017diffeq}, `scipy.integrate` (Python) \cite{virtanen2020scipy}.
   Sunt cărămizi de bază pentru integrarea numerică; lucrarea le tratează ca
   componente, nu ca soluție completă, și le compară sistematic.

2. **Toolkit-uri de modelare epidemiologică** — soluții la nivel mai înalt:
   EpiModel (R, modele pe rețele) \cite{jenness2018epimodel}, Covasim
   (Python, agent-based COVID-19) \cite{kerr2021covasim}, CovidSim / Report 9
   Imperial College (microsimulare) \cite{ferguson2020impact}. Acoperă bine
   un singur ecosistem / o singură paradigmă, dar nu compară cross-limbaj și
   nu integrează un sistem web colaborativ.

3. **Calibrare bayesiană** — Stan \cite{carpenter2017stan}, NIMBLE
   \cite{devalpine2017nimble}. Oferă cuantificarea incertitudinii (MCMC/HMC),
   contrast cu Nelder-Mead determinist folosit aici; menționat ca direcție
   viitoare, nu ca substituent.

4. **Platforme de forecast / agregare** — COVID-19 Forecast Hub
   \cite{cramer2022forecasthub}. Se concentrează pe agregare și diseminare de
   prognoze (ensemble), nu pe un toolkit de modelare reutilizabil.

5. **Poziționare** — contribuția lucrării este la intersecție: benchmarking
   ODE comparativ multi-limbaj + platformă web integrată cu RBAC pe studii +
   evaluare empirică sistematică. Distinct de bibliotecile mono-limbaj și de
   platformele epi specializate care nu au această integrare de sistem.

## Citări noi de adăugat în `docs/bibliography.bib` (6)
- `jenness2018epimodel` — EpiModel (JSS 2018)
- `kerr2021covasim` — Covasim (PLOS Comp Biol 2021)
- `ferguson2020impact` — Imperial Report 9 (techreport 2020)
- `carpenter2017stan` — Stan (JSS 2017)
- `devalpine2017nimble` — NIMBLE (JCGS 2017)
- `cramer2022forecasthub` — COVID-19 Forecast Hub (PNAS 2022)

## Pași
1. Scriere plan (`.md`) — *acest fișier*.
2. Inserare `§sec:lucrari_inrudite` în cap. 1.
3. Adăugare 6 intrări BibTeX.
4. Build `latexmk` — verificare rezolvare citări.
5. Commit (fără trailer Co-Authored-By) + push.
