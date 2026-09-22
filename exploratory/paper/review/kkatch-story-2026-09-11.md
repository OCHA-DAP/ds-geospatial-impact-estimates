# KKatch's story-v3 review, migrated off the public layer — 2026-09-11 → 2026-09-22

KKatch left 23 annotations on the PUBLIC Hypothesis layer for
`https://ocha-dap.github.io/ds-geospatial-impact-estimates/story-v3/` on 2026-09-11, and Zack
replied there (19 annotations, 2026-09-14). Public annotations expose quoted excerpts of the
gated page through the Hypothesis API, so on 2026-09-22 all 42 were copied into the private
group **GIE scroll story (CHD)** (`ibGRdE9j`), tagged `migrated-public` plus `from-kkatch` /
`from-zack`, each body prefixed with its original author and date. Thread structure was
rebuilt: every reply points at its migrated parent.

Only an annotation's own author can delete it, so removing the public originals needs KKatch
for her 23. Migration script: session scratchpad `migrate_kkatch.py`.

## Anchoring

The story was rewritten twice after these comments were written (KKatch's own rounds 1–2, then
Leo's round on 2026-09-22), so most of the quoted passages no longer exist. Where a quote still
matched, the original selectors were copied verbatim. Where the passage had been rewritten, the
copy was re-anchored to the successor passage below and the original quote kept in the note
body. Each successor was asserted to occur exactly once in the republished text.

| # | Quoted in Sep | Anchored now |
|---|---|---|
| 1 | “U's Copernicus Emergency Management” | re-anchored to “The Copernicus Emergency Management Service (EMS)” |
| 2 | “The response begins” | unchanged |
| 3 | “relating detected damage to debris tonnage” | re-anchored to “turns detected damage into an estimate of debris tonnage” |
| 4 | “AOIs” | re-anchored to “eight coastal areas” |
| 5 | “74,705” | re-anchored to “75,118 buildings flagged” |
| 6 | “Two further products arrived in the same window but are not evaluated here: HOT's fAIr, an…” | re-anchored to “Two further products arrived in the same window but are not evaluated here.” |
| 7 | “A stack of assessments of the same disaster: PDFs, shapefiles, dashboards. Different metho…” | re-anchored to “After a disaster, responders can end up with several damage assessments” |
| 8 | “Even here, on identical buildings, the six count anywhere from 5,362 to 25,882 damaged.” | re-anchored to “Even here, on identical buildings, the six count anywhere from 5,443 to 25,882 damaged.” |
| 9 | “One caveat carries through: this holds inside an area already known to be badly hit.” | unchanged |
| 10 | “Ranking orders that zone; it does not find one, and it never names a building.” | re-anchored to “It cannot say where that zone is, and it cannot point to a building.” |
| 11 | “out-rank every single one of them.” | re-anchored to “beats the ranking from any single assessment” |
| 12 | “the same area” | re-anchored to “none covers the same ground as another” |
| 13 | “During this response, an ad hoc viewer our team stood up within days let responders see wh…” | re-anchored to “Within days the OCHA Data Science team stood up an ad hoc” |
| 14 | “and it needs a shared picture of who has looked where to work.” | re-anchored to “A shared, live picture of which analyses have been produced and where they looked.” |
| 15 | “(three of the six reach a Spearman ρ of 0.7 or more against the Copernicus EMS ordering)” | re-anchored to “(three of the six agree closely with the Copernicus EMS ordering)” |
| 16 | “but the reference is silent” | unchanged |
| 17 | “For responders and response coordinators” | unchanged |
| 18 | “For evaluators: keep testing this methodology across different crises, and build the syste…” | re-anchored to “For evaluators: repeat this evaluation in other crises, and make it routine.” |
| 19 | “In the immediate aftermath, responders need to know where the damage is. Satellite-based d…” | re-anchored to “In the immediate aftermath of an earthquake, responders need to know where the damage is.” |

5 of KKatch's comments are page notes with no anchor; they carry over as page notes.

## The threads


**KKatch** — page note

> At the end here, suggest a short line on what the purpose of this GitHub is - is to explain how to make use of it operationally? This opening slide is like the summary so the reader needs to know up front where it's going.

  - **Zack replied:** Added a sentence at the end of the opening: the story evaluates the assessments from Venezuela and asks what responders can, and cannot, do with them.


**KKatch** — “U's Copernicus Emergency Management”

> What is the EU's Copernicus EMS - why are they the 'character' in the story?

  - **Zack replied:** Quick Note: this annotation got re-anchored to the end which is not where you anchored originally (it was in the beginning) Good question, i changed it so that here it's introduced similar to the other products... with a few more details Why it becomes the reference is explained where we start measuring, on "The baseline".


**KKatch** — “The response begins”

> As a reader, I feel like I start entering into the timeline and technical component without really understanding the context or what the real issues of concern are. Therefore I would suggest putting in as a second slide some context before you go into 'The response begins" I suggest the context cover: First, I think you need a new slide something simple that helps the reader to understand the problem that satellite damage assessments solve, their limitations, and why that poses challenges to responders. For example, what used to happen after an earthquake (before we had these type of assessments)? What do these assessments help with (ie. to determine where to deploy SAR, potential people in need humanitarian assistance)? What are the downsides of satellite damage assessments (ie. foreshadow why you can have assessments that come up with such different levels of building damage, or why it might show a building damaged when it's not), And therefore why is it a challenge for humanitarian's that there are so many assessments now? 2) You need to briefly explain what the Centre's role was in Venezuela (later you reference a 'viewer') and its connection to Copernicus EMS. Otherwise you go straight into Copernicus and the reader doesn't understand why.

  - **Zack replied:** Good points -- tried to integrate points by: 1. The opening 2 views explain a bit more about satellite assessments and what they try to solve 2. 2nd view/card explains that our team was tracking them for the UN's assessment and analysis group. As i explain inthe next comment, Copernicus EMS should not really be 'the character' . They deserve some special explanation/framing for analysis so i've changed it so that the next card (3) introduces Copernicus EMS as a product like the others, and "The baseline" later explains why it is the reference. The wider "why so many, why is that hard" point is on the coordination card.


**KKatch** — page note

> Just to note that the overlay of each assessment is very good and really helps.


**KKatch** — “relating detected damage to debris tonnage”

> Not sure I understand this? Meaning it detects where there is debris tonnage or the data that comes from it giving an estimate of debris tonnage based on the damage?

  - **Zack replied:** rephrased


**KKatch** — “AOIs”

> spell this out. There's a lot of acronyms so avoid where you can.

  - **Zack replied:** Fixed, thanks. "AOIs" is now spelled out as "eight coastal areas" in the University of Houston step (Part one, "Additional assessments"). Because the wording changed, this annotation lost its anchor when the page was republished on 14 Sep, so it now shows under the Orphans tab in the sidebar rather than in place. Same for the other comments whose quoted text we edited in this pass.


**KKatch** — “74,705”

> suggest inserting "buildings" after the figure to keep it consistent with previous slides.

  - **Zack replied:** inserted


**KKatch** — “Two further products arrived in the same window but are not evaluated here: HOT'”

> This is quite technical, you could perhaps streamline to "Two further products arrived in the same window but are not evaluated here" and then put the note more detailed explanation in the methodology. The fuller explanation interrupts the flow.

  - **Zack replied:** i made it basically a footnote w/ in this text box, but could remove if distracting


**KKatch** — “A stack of assessments of the same disaster: PDFs, shapefiles, dashboards. Diffe”

> This is great, but give a bit more info as to why this is hard for humanitarians. The S&R audience probably have a pretty good idea, but for those providing these assessments giving them a clear picture of why this is difficult - the types of decisions that have to be made and why having different assessments makes that harder – will be very helpful and eye opening to them. You want to give this audience the "ah-ha moment" now I get it why this would be hard.

  - **Zack replied:** Added two sentences: what a coordinator has to decide in those first days, and that answers this far apart cannot all be right while teams still have to be sent somewhere. Kept short on purpose. The viewer paragraph now sits here too, since this is the problem it was built for.


**KKatch** — page note

> It took me a few reads to get this and I wonder if it's just a placement issue. I wonder if this would be better placed in the next section after the questions and before the baseline - meaning the first step is looking at where the assessments can be compared in relation to where Copernicus was operating. I would also suggest deleting "manual mapping on very-high resolution imagery, not modeling). I don't think it's necessary to understand the story and so anywhere you can cut technical detail I would.

  - **Zack replied:** im not entirely sure what this links to as it's not an annotation


**KKatch** — “Even here, on identical buildings, the six count anywhere from 5,362 to 25,882 d”

> Very good, it gives an idea of the challenge.

  - **Zack replied:** :-)


**KKatch** — page note

> The Answer and the blurb at the bottom of the graph "Even on the most generous reading..." Is good. It needs to be its own box and pulled out. The answer is too buried. I want to see the answer and analysis before I look at the graph - it helps the reader to understand it.

  - **Zack replied:** hmm i tried putting the answer right on top of the plot, but i thought it disturbed the plot flow... idk if we could think of another place to put it


**KKatch** — “One caveat carries through: this holds inside an area already known to be badly ”

> This part of the answer is good but then the caveat confused me - meaning we couldn't say the same for another area where EMS weren't on the ground verifying?

  - **Zack replied:** its a bit confusing I agree.... 1. the ranking only works well in the overlaping core zone (Where damage is worse) 2. Most products delivered a much wider extent product and if we judge each entire product against all CEMs extents (CEMs was not only in this core area -- they have several other areas, but most of which have very little damage) the ranking doesnt work so well does that make sense, any suggestions to make it clearer, but succinct?


**KKatch** — “Ranking orders that zone; it does not find one, and it never names a building.”

> This didn't make sense to me, so perhaps it needs to be reworded.


**KKatch** — page note

> The conclusion at the bottom of the graph is good and should be its own box to the side. Also does using the assessments then help to overcome the issue raised in the slide above that ranking by neighborhood only works where it's in an area already known to be damaged? If so, I think it should be clearer that by using the assessments together you can use it not only within a neighborhood to identify with greater confidence what buildings are damaged, but also in areas where you may not have an EMT deployed yet (presumably). Postscript :) I see you then go back into the neighborhoods with the next slide.

  - **Zack replied:** The key sentence is now its own highlighted strip under the chart, with the explanation above it. On your question: no, combining does not fix the known-zone problem. Agreement ranks neighbourhoods better than any single assessment inside the zone Copernicus had already mapped, but across the wider ground each assessment covered, all the rankings weaken, combined or not. The caveat on "Ranking neighbourhoods: the answer" now says so. Finding the zone in the first place is still the open problem.


**KKatch** — “out-rank every single one of them.”

> Maybe this sentence could be reworded, I had to read it a few times to understand it.

  - **Zack replied:** yeah this got reworded i believe to: "ranking cells by how many assessments agree beats the ranking from any single assessment" --- but this annotation lost it's place fyi


**KKatch** — “the same area”

> Same area or had the same coverage? Cause there is a place where all six overlap.

  - **Zack replied:** reworded for clarity


**KKatch** — “During this response, an ad hoc viewer our team stood up within days let respond”

> This feels like it comes out of nowhere and it needs some clarity eg. "who had looked where" - meaning responders to see what satellite data was available? Part of what gap and what does 'nothing had planned for it'. Perhaps this needs to be part of the beginning context - because this is the first time we're seeing what role the Centre had this.


**KKatch** — “and it needs a shared picture of who has looked where to work.”

> ? Meaning this is what we provided through the 'viewer' that can put all the assessments together?


**KKatch** — “(three of the six reach a Spearman ρ of 0.7 or more against the Copernicus EMS o”

> maybe put in the technical brief unless you think this will be widely understood.

  - **Zack replied:** removed, its in charts anyways.


**KKatch** — “but the reference is silent”

> What do you mean by 'reference is silent'

  - **Zack replied:** this annotation lost it's anchor when i addressed it, but it is addressed and fixed in the conclusion section now.


**KKatch** — “For responders and response coordinators”

> Make each 'audience' in bold or brighter so it stands out.

  - **Zack replied:** good idea- done


**KKatch** — “For evaluators: keep testing this methodology across different crises, and build”

> I didn't really understand this one, but as long as it's using language that evaluators understand that's fine.


**Zack** — “In the immediate aftermath, responders need to know where the damage is. Satelli”

> 

