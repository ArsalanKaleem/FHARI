# Pre-registration — Phase A7 (targeting, regret, value of information)

**Status: FROZEN 2026-10-20** (researcher decisions of 2026-10-20 incorporated). Written before any
A3, A4 or A7 result exists. The frozen copy is `prereg_A7_2026-10-20.md`; its SHA-256 is recorded in
`decision_log.md`. Any later change is a logged deviation with date and reason. No objective,
threshold, candidate rule or estimator is chosen or promoted after seeing H5 results.

## 1. Question and hypotheses
- **H5:** targeting flood-resilience road protection with open facility data (layer A) forgoes a
  measurable share of the achievable benefit, relative to targeting with full information.
- **H2 (A7 part):** the open-data bias differs by outcome (A2 expectation: added delay overstated
  about 4.5x, isolation about 8 %). A small regret under the isolation objective is a legitimate,
  publishable finding. We do not search for an objective that makes regret large.

## 2. Flood scenarios (inputs)
- **Mask version:** v1 (A1 as built) and v2 (v1 minus dry-season persistent-water pixels; rule in
  decision_log 2026-10-20). A7 base = **v2 if v2 meets the pre-registered success criterion, else v1**;
  the other version is reported as sensitivity. Decided from validation only, before A7 runs.
- Base: 2022 event, closure rule D = 3 flood-days, T = 0.6 of edge length, bridges never closed.
- Secondary: 2025 event (base window Aug-Oct; sensitivity 1 Sep-15 Oct), same rule.
- Sensitivity: the 3 x 3 (D, T) grid; bridges closable; **embankment: trunk and primary roads never
  closed**.
- All results are exposure-based scenarios, not observed closures.

## 3. Village categories under flood
- Baseline (normal-roads) travel time uses RHAI snapping (nearest node), unchanged.
- **No mapped road access:** village farther than 1 km from any road node. Separate category in every
  table; not counted as isolated, covered or delayed.
- **Isolated (flood):** no flood-open node reachable from a facility within 1 km of the village.
  Otherwise the village's flood travel time is the minimum over reachable nodes within 1 km of
  (network time at that node); the off-road leg is not timed (as in RHAI).
- Sensitivity radii 0.5 and 2 km. The three villages on visibly dry raised roads (2163, 2194, 2154) are
  listed with their status in every configuration.

## 4. Intervention, candidate set, budget
- **Unit ("link"):** a maximal run of consecutive closed edges between junctions (degree-2 nodes
  contracted), both directions together. "Protect" = reopen every edge of the link in the flood
  scenario (raised road / culvert).
- **Candidate set (common to all states):** union of the top N = 200 links under each of layer A,
  layer B and the ensemble mean, ranked by single-link reopening gain in the primary objective (for the
  ensemble, mean gain over draws). Sensitivity: N = 1000.
- **Budget:** K in {5, 10, 20, 50} links; sensitivity K = 100; plus a length-weighted budget (sum of
  link km <= L, L = length of the K = 20 base solution). Unit costs are unsourced; illustrative ranges
  only (`parameters_to_source.md`).

## 5. Objectives (all reported, whatever the outcome)
For allocation x and facility state s, village flood travel time t_v(x, s) per §3 (+inf if isolated).
- **Primary — coverage:** C_T(x, s) = sum_v w_v 1[t_v(x, s) <= T] / sum_v w_v; T = 60 min base, 30 and
  120 min sensitivity. Villages with no mapped road access are excluded from numerator and
  denominator and reported separately.
- **Secondary:** isolated population I(x, s); added person-hours among villages reachable both
  normally and under flood, H(x, s).
- **Weights:** shares and ratios (C_T, regret ratios, bias ratios) use the RHAI 2 km buffer population;
  absolute people and person-hours use the deduplicated 2 km partition, reported as "people within 2 km
  of a mapped village".

## 6. Optimisation
- **Greedy** with exact re-routing (A2 code path): add the candidate link with the largest marginal
  gain; ties broken by link id. Primary method.
- **Check:** ILP on the additive approximation (per-link single-reopening gains per facility state),
  solved exactly per K, reported next to greedy with set overlap. If Jaccard < 0.8 at K = 20, both are
  reported; greedy stays primary.

## 7. Facility information states
- **A:** open data only. **B:** open data + 583 geocoded PPHI facilities.
- **Ensemble:** draws d = 1..N from A4 (each of the 741 unlocated PPHI facilities placed or omitted per
  the A3 calibrated probabilities, "no match" = omitted). The ensemble is the **truth proxy**; its
  realism depends on A3 calibration (stated as a limitation).

## 8. Regret, EVPI, value of information
V_d(x) = objective of allocation x evaluated on draw d; x*_d = allocation optimal for draw d;
x_ens = argmax_x E_d[V_d(x)]; empty = no protection.
- **Headline regret (share of achievable benefit):**
  Regret(x) = E_d[V_d(x*_d) - V_d(x)] / E_d[V_d(x*_d) - V_d(empty)].
- **Also reported:** absolute regret E_d[V_d(x*_d) - V_d(x)] in deduplicated people (coverage) and
  person-hours; coverage-normalised RegretC(x) = E_d[V_d(x*_d) - V_d(x)] / E_d[V_d(x*_d)].
- **Tiny-gain rule:** if the achievable gain E_d[V_d(x*_d) - V_d(empty)] is below 1,000 deduplicated
  people (coverage) at the given K, or its 95 % interval includes 0, the ratio is not reported as the
  headline; absolute values with intervals are reported instead.
- Report for x_A, x_B, x_ens. **EVPI** = E_d[V_d(x*_d)] - E_d[V_d(x_ens)]. Intervals: percentile
  bootstrap over draws (2,000 resamples, seed 20221001). Overlap: Jaccard(x_A, x_B), Jaccard(x_A,
  x_ens), Jaccard(x_B, x_ens), and the mean Jaccard of each with x*_d.
- **Per-district value of information (EVPPI_k):**
  EVPPI_k = E_{d_k}[ max_x E_{d_-k}[V(x) | d_k] ] - max_x E_d[V(x)],
  estimated with the additive per-link approximation of §6 (draws re-weighted by their district-k
  realisation); validated against exact greedy for the top 3 districts. Output: ranking of districts
  for geocoding effort.

## 9. Equity variant and H2 outcomes
- **Priority weights (Atkinson-style, isoelastic):** w_v(eps) = pop_v * (t_v^normal / t_med)^eps,
  eps in {0, 1, 2}; t_v^normal = normal-roads travel time under the evaluated facility state, t_med its
  population-weighted median; eps = 0 is the efficiency objective. Frontier: for each eps-optimal
  allocation, efficiency = C_60 with eps = 0 weights; equity = Atkinson index A_1 of flood travel time
  across people (isolated villages at the T = 120 cap for this index only).
- **H2 bias ratios** (A vs B; A vs ensemble mean): median travel time, added person-hours, isolated
  population, coverage C_60; by event, (D, T) and mask version; 95 % intervals from a village bootstrap
  stratified by district (2,000 resamples).

## 10. Not changed after results
Objectives (§5), candidate rule (§4), budgets, regret definitions (§8), mask-choice rule (§2) and
isolation definition (§3) are fixed here. Deviations are logged with date and reason.
