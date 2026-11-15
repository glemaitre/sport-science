# Writing the lecture notes

Read this before adding or revising a lecture. The project mechanics are in the root [AGENTS.md](../AGENTS.md).

## The reader

Guillaume is building these notes to learn the physiology, not to be reminded of it. A sentence that only works if the reader already knows the word has failed.

- Define the word, then use it. A gradient is a difference between two sides of a membrane: more of an ion on one side than on the other. Ions move by themselves from the crowded side toward the scarce side. That costs no ATP. ATP is spent pushing them back. Say it that way the first time. "Downhill" and "down its gradient" are not definitions.
- The same rule covers free energy, acronyms, and named proteins. "Free energy" in these notes means the useful energy from splitting one ATP, which is larger when ATP stays high and ADP stays low. AMP is adenosine monophosphate. IMP is inosine monophosphate. A glucosyl unit (French: glucosyle, unité glucosyle) is one glucose residue inside glycogen. Glycolysis in French is glycolyse.
- Give a structural word a job in the same sentence. The T-tubule is the tube of outer membrane that reaches into the fibre. The ryanodine receptor is the calcium door of the sarcoplasmic reticulum. Tropomyosin is the protein that covers the binding sites on actin.
- Pathway shares are uncertain by about ±10 percentage points. Say so instead of picking a false precision. When a mechanism is still debated, say that it is the common reading.
- Direct teaching prose. Both languages carry the same claims. Do not start the open questions at the end of lecture 1 or lecture 2 unless asked.

## What a contraction spends

Three ATPases. Myosin uses one ATP per cross-bridge cycle. The sodium–potassium pump moves 3 Na+ out and 2 K+ in per ATP. SERCA moves 2 Ca2+ back into the sarcoplasmic reticulum per ATP. The two pumps together are about 20–40% of the ATP of a contraction (MacIntosh). Do not split that range into a sodium share and a calcium share. The cross-bridges take the rest. The share of the pumps rises when the fibre fires more often.

The action potential and the calcium release are the ions moving toward the side where they are scarce. The power stroke spends energy stored when ATP hydrolysis tensed the head, the way a drawn spring stores energy. A new ATP is what lets the head let go of actin. Without ATP the bridge stays shut: rigor. Calcium decides whether a pull is allowed.

The ATP pool is about 5–8 mmol/kg of wet muscle. It is a concentration the cell defends, not a fuel tank. Even all-out, it usually falls only 1–2 mmol/kg. Alone it lasts about 15 s at ~200 W (~75% VO2max, ~0.4 mmol/kg/s) and under 2 s all-out (~900 W, ~3.7 mmol/kg/s). From the first pedal stroke it has to be remade about as fast as it is used. Whole-muscle turnover rises about 100-fold from rest to a maximal effort.

## The three supplies

They overlap from the first seconds. The textbook sequence "phosphocreatine, then glycolysis, then oxygen" is rejected in lecture 1.

- Phosphagen: creatine kinase, `PCr + ADP + H+ → ATP + creatine`. The proton on the left is why the reaction also buffers a hard effort. Myokinase is `2 ADP → ATP + AMP` and makes no new purine.
- Glycolysis to lactate: about 3 ATP per glycogen glucosyl unit, about 2 per blood glucose, because hexokinase spends one ATP (`glucose + ATP → glucose-6-phosphate + ADP`). Lactate dehydrogenase is `pyruvate + NADH + H+ → lactate + NAD+`. It regenerates NAD+ so glycolysis can continue. Lactate is a fuel and a redox valve, not the acid and not a dead end.
- Oxidative phosphorylation: about 30 to 36 ATP per glucose, about 100 to 130 per palmitate after beta-oxidation. Older tables say 36 and about 130. Oxygen is the final electron acceptor, not the fuel.
- Gross cycling efficiency is about 20–25%. One litre of oxygen is about 21.1 kJ on carbohydrate and 19.6 kJ on fat. The 20–25% is the whole path from fuel to the pedal, not the mitochondrial P/O ratio.

Gastin 2001: aerobic and anaerobic supplies are equal near 75 s of maximal effort, not at 2–4 minutes. Inside 90 s all-out the aerobic share of each half-minute is roughly 30%, then 70%, then 90%. A second 30 s sprint after a few minutes is already more aerobic (about 40% in one study).

## Creatine and recovery

Recovery of a sprint is the aerobic refill of phosphocreatine: `creatine + ATP → phosphocreatine + ADP`. Fast phase half-time about 20–30 s. Near-complete restoration takes from under 5 minutes to more than 15 minutes. The reason for two phases is still debated. Acidity, blocked blood flow, and fast-twitch fibres slow it. Riding above threshold between efforts leaves less spare ATP for the refill.

The creatine pool is not kept stable by the ATP/ADP couple. Diet is about 1 g/day and kidney-plus-liver synthesis about 1 g/day. Muscle takes it up through SLC6A8. About 95% of the ~120 g in a 70 kg adult is in skeletal muscle. Creatine is lost by spontaneous conversion to creatinine (about 1.5–2% per day, excreted by the kidney) and in the urine when plasma creatine exceeds what the proximal tubule reabsorbs. Creatine kinase only moves a phosphate. Those daily amounts are the teaching figures from Wyss and Kaddurah-Daouk, *Physiological Reviews* 2000; check that review before writing a tighter number.

During steady riding, mitochondrial creatine kinase recharges creatine and the phosphocreatine shuttle carries the phosphate to the myofibrils. Creatine and phosphocreatine spread faster than ADP and ATP because they are smaller, and the fibre can hold a larger concentration difference of them.

## Lactate and acid

Do not write that lactate binds H+ to hide the acid. Lactate dehydrogenase consumes a proton. At muscle pH almost all of the product is lactate−, because lactic acid has a pKa near 3.9. The protons that acidify the fibre come from ATP hydrolysis and from the glyceraldehyde-3-phosphate dehydrogenase step. A net glycolysis often written for teaching is `glucose + 2 ADP + 2 Pi → 2 lactate− + 2 H+ + 2 ATP + 2 H2O`. Buffers: the creatine kinase reaction consumes H+, bicarbonate is `H+ + HCO3− ⇌ CO2 + H2O`, and phosphate takes some. MCT1 and MCT4 export lactate− together with H+. This chemistry was explained in conversation and is not yet a section of the notes. Add it only when asked.

## Intensity, fuel, and zones

Above a few minutes, almost all ATP is oxidative. Absolute fat oxidation peaks near 60–65% of VO2max (FatMax). That is not race pace, and % of VO2max is not % of PMA.

PMA is the best mean power over about 5 minutes (4–6 is accepted). It sits a little above the lab power at VO2max because the anaerobic contribution is still there. Grappe's ESIE zones, as written in lecture 1, are population averages and the published bands differ by a few points:

| Zone | % of PMA | What the notes say |
| --- | --- | --- |
| I1 | 40–50% | Recovery, almost all fat |
| I2 | 50–60% | Endurance, SV1 near the top, the long fat-use ride |
| I3 | 60–75% (sometimes printed 60–70%) | Between thresholds, carbohydrate rises |
| I4 | 75–85% | SV2 |
| I5 | 85–100% | Near VO2max, about 5–10 min |
| I6 | about 110–180%, sources differ | About 30 s to 1 min, glycolysis |
| I7 | maximal, 1–10 s | Phosphocreatine |

FatMax falls near the top of I2 and the start of I3. Critical power is `Tlim = W′ / (P − CP)`, the heavy/severe boundary, and it is not the same wattage as lactate threshold or maximal lactate steady state.

## Mitochondria, when a later note touches them

The outer membrane is not the proton barrier. The inner membrane is the seal, folded into cristae. Endurance training adds mitochondrial volume and, more tightly linked to VO2max, cristae density. It does not invent a more efficient respiratory enzyme. About 10 protons are pumped per NADH and about 6 per FADH2. About 2.5 ATP per mitochondrial NADH and 1.5 per FADH2 once export is counted, which is close to four protons per ATP the myofibril can use. The c-ring is about eight subunits and three ATP per turn. Uncoupling protein 3 and how much leak it carries on the bike are unsettled; do not pick a verdict. A little tighter coupling does not move gross efficiency from 20% to 30%.

## Diagrams in the notes

Films live in `lectures/cycling-physiology/movies/`. Embed one with a `video` tag and a caption that links to the same file. The build copies those files only into the English site, so a French page links with `../../cycling-physiology/movies/`. The on-screen text of the current films is English, so the French caption says so. `how-a-muscle-spends-atp.mp4` belongs with the cross-bridge in lecture 1. `where-the-atp-is-remade-the-mitochondrion.mp4` belongs with the two doors in lecture 2.

Section 6 of lecture 1 opens with the full pathway map (fuels, pyruvate, lactate, mitochondria, phosphocreatine, ATP, cross-bridges, ion pumps). The map is about production. The last two boxes only mark where ATP goes. The equation charts come after it: the first three make ATP, and the last is the spending reaction. Each one has a sentence saying what the transformation is. Keep that order. One chart cannot hold every equation.

## Discussed, and deliberately not in the notes

Add these only when asked.

- How muscle glycogen is rebuilt (GLUT4, hexokinase, phosphoglucomutase, UDP-glucose, glycogen synthase, branching enzyme) and how to load it. The loading range mentioned in conversation, about 7–12 g of carbohydrate per kg per day for 24–48 h with a taper, plus about 1 g/kg/h after exercise, was a practical range, not one study.
- A training prescription for fat loss. The notes have the ESIE table and FatMax. They do not say which ride to do.
- The full lactate and acid accounting above, beyond the statement that lactate is not the acid.
