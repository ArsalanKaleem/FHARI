# Related-work note (1 page) — Paper A

Read in full on 2026-10-20. **Verified** = read in the primary text this session. **Unverified** =
not checked against a primary source. This covers three works, not a literature review, so it
cannot support a "first study to…" claim on its own (see the last section).

## 1. Khan, Lauer & Marwan (2026), *Spatial Information Research* 34(4):34, doi:10.1007/s41324-026-00695-8
Source read: Oxford ORA author-accepted manuscript (18 pp.). Bibliographic record from the ORA landing page (verified).
- **Event and data (verified):** 2025 monsoon floods, Sindh + Punjab. Flood = UNOSAT binary extents (20 m, S1 SAR + S2), snapshots "as of 10/11 July 2025" (early season, not the later Indus riverine peak). Roads = OSM (HOT export), **major classes only** (residential/service/track dropped). **Facilities = OSM (HOT export) only**; no register, and completeness is never discussed. Population = WorldPop, used only for exposure counts.
- **Method (verified):** segment unusable if ≥ **60 %** of 20 m sample points are flooded; 50 %/70 % described as "qualitatively similar" (no numbers given). Length-weighted, undirected graph; **distance, not travel time**. Origins = "DHQ", represented by **district polygon centroids**, not hospital locations. Facility → nearest centroid distance, classified at 5/10/15 km; no path → "disconnected".
- **Results (verified):** 40 of 6,948 major segments unusable (0.6 %, 2.99 km); 84.8 % (Sindh) / 75.9 % (Punjab) of facilities "affected" at 5 km. Primary care worst affected. No population-weighted access, no criticality ranking, no costs, no optimisation; protecting "a small number of critical road corridors" is offered as a conclusion only, not tested.
- **Relevance:** the closest prior study (same province, 2025 floods). Its facility layer is essentially our Scenario A, so its headline numbers carry exactly the omission bias Paper A measures. Our 60 % base threshold matches theirs, so it can be cited for comparability.

## 2. Paracha, Aftab & Heyns (2023-11-06), World Bank *Transport for Development* blog, "Pakistan: Devastating floods have widened spatial disparities"
- **Verified (blog text):** 2022 floods (Aug–Oct shock vs a typical-monsoon baseline). Multi-modal (walk + vehicle) travel time from populated locations to schools, health facilities and administrative centres. Population-weighted, aggregated to district/tehsil, combined into an accessibility index. Jacobabad: "a 10 hour increase in average travel time per person to reach a health facility". Sujawal markets: 2.6 → 13 h.
- **Unverified:** the underlying model, flood layer, facility source and road data. The blog cites no report or paper. Do not cite its methods; cite only the figures, as a blog.
- **Relevance:** the only 2022 Sindh population-weighted flood travel-time estimate we have. Useful as an order-of-magnitude benchmark, but not comparable at village level and silent on facility completeness.

## 3. Petricola, Reinmuth, Lautenbach, Hatfield & Zipf (2022), *Int. J. Health Geographics* 21:14, doi:10.1186/s12942-022-00315-2
Source read: PMC9559768, full text.
- **Verified:** Cyclone Idai, Mozambique 2019. Flood = WFP (90 m) + UNOSAT S1 (10 m) masks merged. OSM roads (2021 snapshot) and 1,059 OSM facilities (ohsome); facility "completeness … not guaranteed". Two travel-time methods: openrouteservice isochrones vs a MAP friction-surface least-cost raster. Flooded OSM **nodes** removed, with no inundation-fraction threshold (the authors flag the dry-node crossing error). Lost driving access ≈ 0.80 M (raster) vs ≈ 0.53 M (network). The ~300 k gap is attributed mainly to incomplete OSM road mapping (road length in flooded areas ~1.9× after the event).
- **Criticality (verified):** targeted edge betweenness (TEBC): population-nucleus → facilities within 20 km, normalised by destination count. A drop after flooding marks a critical segment; a rise marks a backup road. The authors advise against population weighting by default, because remote communities can become "invisible". No economics or optimisation.
- **Relevance:** precedent that **data incompleteness changes flood-access estimates by a large share**, but for *roads* and *method choice*, not facility omission, and without decision consequences. TEBC is a candidate generator for A7's link set. Their warning about population weighting supports our equity-weighted variant.

## What this implies for Paper A's novelty (provisional)
None of the three (a) quantifies **facility-register omission** under flood conditions, (b) treats the missing facilities **probabilistically**, or (c) evaluates a **targeting decision** (which links or facilities to protect) and its **regret / value of information**. Paper A is defensibly distinct from these three on (a)–(c). It is **not** distinct on: flood-conditioned network removal with a segment-fraction threshold (Khan et al.), criticality/backup-road identification (Petricola et al.), or population-weighted flood travel-time loss in Sindh (World Bank blog).

**Before any novelty sentence goes in the manuscript (not done):** search value-of-information / robust or regret-based facility-location and network-protection literature, and recent flood-accessibility work. One unread hit to check: arXiv 2607.16668 (flood-amplified congestion and healthcare access, US cities). Status: **unverified, not read**. → Done 2026-10-22, see below (arXiv 2607.16668 still not read).

---

## Novelty search (2026-10-22): VoI, robust and reliable facility location, road-protection decisions

**Search log (web; "extended" mode for niche queries):** (1) value of information + spatial data quality +
health facility location; (2) pre-disaster road investment + healthcare access + flood + stochastic
programming; (3) incomplete facility master lists / OSM + accessibility bias; (4) minimax regret + robust
facility location + data errors; (5) EVPI / VoI + infrastructure resilience + disaster; (6) sensitivity of
accessibility to missing / mislocated facilities; (7) 2022 Pakistan floods + healthcare accessibility;
(8) facility-data omission + allocation decisions + OSM; (9) aggregation error in location models;
(10) reliable facility location / facility failure / incomplete information / misestimation.
**Verification levels:** *read* = full text read this session; *record* = abstract or bibliographic record
read on a publisher or repository page; *snippet* = search-result summary only (do not cite specifics).

### A. Same decision family; facility data taken as given (closest analogues)
- **Akhlaghi, Campbell & Demir (2023), "The Flood Mitigation Problem in a Road Network", arXiv:2302.07983 — read.**
  Deterministic network-design model: choose road segments to upgrade under a budget to minimise
  population-weighted travel time between population centres and healthcare facilities. Vulnerable roads are
  segments inside the 100-year floodplain (Iowa Flood Center maps); case study Coralville, Iowa. Using 7 instead
  of 3 facilities improves the objective by 28 % — the facility set matters, but only as a design scenario. Their
  future work states the model "is based on the assumption that the locations of the HCFs are given". No
  facility-data uncertainty, regret or value of information.
- **Salman, Peeta, Günneç & Viswanath (2010), "Pre-disaster investment decisions for strengthening a highway
  network", Computers & Operations Research, doi:10.1016/j.cor.2009.12.006 — record.** Two-stage stochastic
  program; uncertainty = random link failure with known probabilities, raised by investment; objective =
  first-responder O-D connectivity and travel cost; knapsack approximation; Istanbul earthquake case.
- **Toplu-Tutay, Hasenbein, Kammer-Kerwick & Kutanoglu (2026), arXiv:2608.26304 — record.** Bi-objective
  two-stage stochastic model: hardening and evacuation for 3,752 Texas hospitals/nursing homes under cyclone
  flood scenarios; the facility inventory is known.
- *Snippet only:* Du & Peeta (bi-level extension); Yücel et al. (dependent link failures); Zhang et al. 2023
  (CACIE, flood hardening as a two-stage program); Alabbad et al. 2021 (STOTEN, flood disruption of access, Iowa).

### B. Uncertain inputs to accessibility estimates (measurement, not decisions)
- **Hierink et al. (2022), Communications Medicine, doi:10.1038/s43856-022-00179-4 — read (PMC).** Six gridded
  population products change 1-hour coverage by > 70 % sub-nationally. Facility data held fixed; the authors note
  facility coordinates "may introduce further uncertainty". Decision consequences discussed, not quantified.
- *Snippet only:* Maina et al. (2019, Scientific Data; SSA public facility database, PMC page blocked); Weiss et
  al. (2020, Nature Medicine 26:1835-8; abstract figures differ between versions — do not quote numbers);
  MFL-vs-OSM completeness comparisons.

### C. Location models under uncertainty / data error
- **Francis, Lowe, Rayco & Tamir (2009), Annals of Operations Research 167:171-208,
  doi:10.1007/s10479-008-0344-z — record.** Error from aggregating DEMAND points, not facility omission.
- *Snippet only:* Snyder (2006) IIE Transactions review; Owen & Daskin (1998); Averbakh & Berman (1997)
  minimax-regret p-centre; Serra & Marianov (1998) regret p-median; Dönmez et al. (2021, Omega) humanitarian
  facility location under uncertainty. These model uncertain demand, travel times or hazards, mostly for siting
  NEW facilities.

### D. Value of information in infrastructure / disaster planning
- *Snippet:* EVPI appears as a diagnostic in stochastic flood-hardening and relief models (e.g. arXiv 2302.10408,
  arXiv 2007.07767), pricing HAZARD information (forecasts / scenarios), not facility-register information.

### E. Reliable facility location (facility-failure models) — the closest OR concept to an omitted facility
- **Snyder & Daskin (2005), "Reliability models for facility location: the expected failure cost case",
  Transportation Science 39(3):400-416, doi:10.1287/trsc.1040.0107 — record.** p-median / UFLP with expected
  transport cost when facilities fail; trade-off curves show large reliability gains for small operating-cost
  increases.
- **Cui, Ouyang & Shen (2010), "Reliable facility location design under the risk of disruptions", Operations
  Research 58(4-1):998-1011, doi:10.1287/opre.1090.0801 — record.** Site-specific failure probabilities, customer
  reassignment; MIP + Lagrangian relaxation + continuum approximation.
- **Berman, Krass & Menezes (2009), "Locating facilities in the presence of disruptions and incomplete
  information", Decision Sciences 40(4):845-868, doi:10.1111/j.1540-5915.2009.00253.x — record.** Customers do not
  know which facilities are operating; expected cost decomposed into travel, reliability and INFORMATION components,
  so the value of advance status information can be priced; stronger centralisation/co-location than with complete
  information. The nearest existing "value of information about facilities" construct — but the information is
  operational STATUS of known facilities, the decision is facility siting, and there is no road network protection.
- **Lim, Bassamboo, Chopra & Daskin (2013), "Facility location decisions with random disruptions and imperfect
  estimation", M&SOM 15(2):239-249, doi:10.1287/msom.1120.0413 — record.** Cost of MISESTIMATING disruption
  probabilities: underestimation raises expected cost more than overestimation; hedging is modest in cost.
  Conceptual link only: open data act like an over-estimate of facility absence, but Paper A's decision is
  road protection, so their asymmetry result cannot be transferred.
- **Yun, Wang, Fan & Li (2017), PLoS One 12(5):e0177104 — read (PMC).** Trial-and-error visiting under imperfect
  status information; US state-capital case; no health facilities; assumed failure probabilities.
- *Snippet:* Church & Scaparra (2007), Geographical Analysis 39(2):129-146, doi:10.1111/j.1538-4632.2007.00698.x —
  fortification against interdiction of facilities (protecting facilities, not roads to them).

### Revised novelty statement (provisional; for the manuscript)
Three established strands meet in Paper A without, in the literature found here, having been combined:
(1) budgeted protection of flood-exposed road links to improve population access to healthcare (Akhlaghi et al.
2023; first-responder variant Salman/Peeta et al. 2010), which takes facility locations as given;
(2) input uncertainty in accessibility estimates (population data: Hierink et al. 2022), which stops at
measurement; and (3) reliable facility location, which values information about the operational STATUS of known
facilities (Berman, Krass & Menezes 2009) and the cost of misestimating failure probabilities (Lim et al. 2013)
for siting decisions. **No study found (i) prices the decision loss (regret) and value of information of
facility-REGISTER omission — facilities that exist and operate but are absent from the planner's data — in a
road-protection decision; (ii) represents unlocated register facilities probabilistically from a calibrated
matcher; or (iii) shows that the open-data bias is outcome-dependent under flooding (large for coverage and
delay, near zero for isolation).** Write "to our knowledge, based on a structured search", cite strands (1)-(3),
and present reliable facility location as the conceptual parent of the omitted-facility idea.
Residual risk: OR work on network design with uncertain destination sets under other terms (e.g. "uncertain
facility availability" in network design, "partial information" humanitarian logistics); arXiv 2607.16668 unread.
