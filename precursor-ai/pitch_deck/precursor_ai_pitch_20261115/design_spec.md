<!-- ppt-master-schema: design-spec/v1 -->
# PRECURSOR AI Pitch - Design Spec

## I. Project Information

| Item | Value |
| --- | --- |
| Project Name | precursor_ai_pitch |
| Canvas Format | PPT 16:9 (1280×720) |
| Page Count | 9 |
| Primary Language | en |
| Target Audience | NASA Space Apps Challenge judges and attendees: technically literate, short on time, not necessarily InSAR or landslide specialists. |
| Communication Intent | Explain the problem and how the platform works first; then persuade the judges that PRECURSOR AI is a credible, reusable use of NASA radar data for the "Dancing with the SARs" challenge. |
| Desired Audience Outcome | Judges can say in one sentence what PRECURSOR AI does, which NASA datasets it uses and why it matters, and they scan the QR code to try the app. |
| Core Message / Ask / Action | Open NASA data in, one usable landslide early-warning map out: PRECURSOR AI sees landslides before they happen, from space. |
| Delivery Context | Primary: presenter-led live pitch of a few minutes on a projected screen. Secondary: the deck is shared with judges as part of the submission and read without a presenter. |
| Artifact Afterlife | Submission artifact for the challenge; reused as the base deck once the Lorem ipsum placeholders are replaced with real results. |
| Reading Mode | balanced |
| Content Strategy | Follow the supplied 9-slide plan: same slide order and titles, plan wording kept, Lorem ipsum placeholders kept as written. Steps 1-4 and Dashboard text on the How-it-works slide reuse the previous deck. |
| Design Style | Mode custom (narrative basis) + visual style ink-wash on the confirmed Night radar dark palette |
| AI Image Acquisition Path | not applicable |
| Generation Mode | continuous |
| Spec Refinement | disabled |
| Speaker Notes | enabled — final Stage-2 proactive policy |
| Custom Animations | disabled — final Stage-2 proactive policy |
| Narration Audio | disabled — final Stage-2 proactive policy |
| Created Date | 2026-11-15 |

## II. Canvas Specification

| Property | Value |
| --- | --- |
| Format | PPT 16:9 |
| Dimensions | 1280 × 720 |
| viewBox | `0 0 1280 720` |
| Margins | 64 px left/right, 56 px top/bottom |
| Content Area | x 64–1216, y 56–664 |

## III. Visual Theme

### Theme Style

- **Mode**: custom
- **Mode References**: narrative
- **Mode Behavior**: Narrative arc over the user's fixed nine-slide order: the unseen warning sign (situation), data nobody can reach (tension), one platform and its pipeline (resolution), NASA data and impact (proof), phased roadmap, team and a scan-the-QR close. Slide titles stay the plan's labels as kickers; one short beat line per page advances the story. Lorem ipsum placeholders stay visible and are marked as to-fill.
- **Visual style**: ink-wash
- **Theme**: Night ink. The ink-wash discipline carried onto the confirmed dark navy field: the navy emptiness is the paper, teal is the ink, and one amber seal square per page is the single warm accent. Cross-page motif: a broad irregular teal brush sweep read as a hillside ridge line with a thin satellite pass arc above it; it is large on the cover and closing and shrinks to a low horizon wash on content pages (continuity job: the slope being watched). The amber seal marks the one thing to notice on a page; on placeholder pages it is the to-fill mark.
- **Tone**: Still, considered, precise; quiet confidence rather than hype.

### Color Scheme

| Role | HEX | Purpose |
| --- | --- | --- |
| Background | #0B1426 | The dark field; carries most of every page |
| Secondary background | #14213D | Rare ink-dark block, table header band, quiet panels |
| Primary | #2DD4BF | Ink: brush sweeps, key words, numerals, rules |
| Accent | #F2994A | The seal: one warm mark per page, placeholders, risk |
| Secondary accent | #5B8DEF | Satellite pass arc, secondary lines, data-source cue |
| Body text | #F4F6FA | Titles and body copy |
| Secondary text | #9AA8C2 | Kickers, captions, annotations, footers |
| Divider | #2A3A5C | Hairline rules and table row lines |

## IV. Typography System

### Font Plan

| Role | Character (Reference) | Primary | English if non-English | Fallback tail |
| --- | --- | --- | --- | --- |
| Title | clean humanist sans, light-to-semibold contrast, large and airy | Segoe UI |  | sans-serif |
| Body | clean humanist sans | Segoe UI |  | sans-serif |
| Label | monospace small-caps kicker and index | Consolas |  | monospace |

- **Title stack**: "Segoe UI", sans-serif
- **Body stack**: "Segoe UI", sans-serif
- **Label stack**: Consolas, monospace
- **Role rationale**: Label carries the confirmed "Consolas labels" pairing for kickers, slide indexes and step numbers on every page.

### Font Size Hierarchy

| Purpose | Anchor Size (px) |
| --- | ---: |
| Body | 24 |
| Title | 42 |
| Subtitle | 32 |
| Annotation | 18 |
| Label | 16 |
| Display | 84 |
| Numeral | 56 |
| Lead | 28 |

## V. Layout Principles

### Deck-wide Direction

- **Hierarchy direction**: Kicker label top-left, then the beat line as title, then content floating in open dark space; the eye ends on the amber seal.
- **Composition tendency**: Asymmetric, scroll-like; emptiness is the structure, few boxed panels; sequences read along a rule or band rather than a card grid.
- **Cross-page continuity**: Kicker label with slide index, the low teal horizon wash, one amber seal per page; cover and closing share the large ridge sweep.
- **Spacing posture**: Open; variable by page rhythm.
- **Spacing anchors**: page margin 64, block gap 32, column gutter 40, corner radius 4, body leading 36

## VI. Icon Usage Specification

- **Primary bundled library**: phosphor-duotone

| Icon Path | Suitable Scenarios |
| --- | --- |
| phosphor-duotone/warning |  |
| phosphor-duotone/cell-signal-slash |  |
| phosphor-duotone/hard-drives |  |
| phosphor-duotone/cursor-click |  |
| phosphor-duotone/download-simple |  |
| phosphor-duotone/wave-sine |  |
| phosphor-duotone/stack |  |
| phosphor-duotone/gauge |  |
| phosphor-duotone/map-trifold |  |
| phosphor-duotone/planet |  |
| phosphor-duotone/mountains |  |
| phosphor-duotone/cloud-rain |  |
| phosphor-duotone/drop-half |  |
| phosphor-duotone/clock-counter-clockwise |  |
| phosphor-duotone/chart-line-up |  |
| phosphor-duotone/seal-check |  |
| phosphor-duotone/globe-hemisphere-east |  |
| phosphor-duotone/rocket-launch |  |
| phosphor-duotone/presentation-chart |  |
| phosphor-duotone/code |  |
| phosphor-duotone/paint-brush |  |
| phosphor-duotone/layout |  |
| phosphor-duotone/brain |  |
| phosphor-duotone/qr-code |  |
| phosphor-duotone/magnifying-glass |  |
| phosphor-duotone/eye-slash |  |
| phosphor-duotone/broadcast |  |
| phosphor-duotone/flag-banner |  |

## VII. Visualization Reference List

| Page | Family | Template | Usage |
| --- | --- | --- | --- |
| P05 | table | record_table | Each NASA source as one record: source name and what it gives the platform |

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Image pattern | Crop Policy | Acquire Via | Status | Reference | text_policy | page_role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## IX. Content Outline

### Part 1: The problem

#### Slide 01 - Title

- **Audience move**: Does not know the project → knows its name and its one-line promise
- **Relationships**: none
- **Composition**: Large ridge brush sweep across the lower field with a thin satellite pass arc above; name and promise float in the emptiness upper-left; amber seal counterweights lower-right
- **Cover impact**: Hook (binding): "Seeing landslides before they happen, from space."
- **Title**: PRECURSOR AI
- **Core message**: Seeing landslides before they happen, from space.
- **Content**: PRECURSOR AI / Seeing landslides before they happen, from space. / NASA Space Apps Challenge: "Dancing with the SARs"

#### Slide 02 - Challenge

- **Audience move**: Assumes landslides strike without warning → sees the warning exists but is out of reach
- **Relationships**: three parallel causes of one gap: warning signs exist; no ground sensors; radar data exists but is unused
- **Composition**: Beat line large on the left; three statements hang from one vertical rule on the right, no cards
- **Title**: Challenge
- **Core message**: The signal exists. Almost nobody can reach it.
- **Content**: Landslides often show weak warning signs first: slow ground creep and heavy rain on saturated soil · Most hillsides have no ground sensors · Radar satellite data exists, but it is huge and technical, so decision makers rarely use it

### Part 2: The platform

#### Slide 03 - Solution

- **Audience move**: Sees the gap → sees one platform that closes it
- **Relationships**: order of five steps: pick an area → find, download and check NASA data → measure ground movement with InSAR → combine with terrain, rain, soil moisture and landslide history → risk estimate
- **Composition**: Governing sentence on the left; five steps ordered down a vertical scroll band on the right; the fifth (placeholder) carries the amber seal
- **Title**: Solution
- **Core message**: One platform that turns NASA radar and environmental data into a landslide early-warning map for any area.
- **Content**: One platform that turns NASA radar and environmental data into a landslide early-warning map for any area / Pick an area on the map / The platform finds, downloads and checks the NASA data / It measures ground movement with InSAR / It combines movement with terrain, rain, soil moisture and landslide history / Risk estimate: Lorem ipsum dolor sit amet, consectetur adipiscing elit. (placeholder, kept)

#### Slide 04 - How it works

- **Audience move**: Knows what it does → can follow the pipeline end to end
- **Relationships**: order of six stages: Acquire → Process (InSAR) → Integrate → Analyze → Risk and explain → Dashboard
- **Composition**: One horizontal brush line as the spine with six stations along it, numerals above and one caption below each; station five carries the amber seal
- **Title**: How it works
- **Core message**: NISAR sees the ground move. Terrain and rain tell us where and when it matters.
- **Content**: Acquire: NISAR, elevation, rainfall, soil moisture, landslide history / Process (InSAR): InSAR turns two radar passes into ground displacement / Integrate: All layers aligned to one common grid, sources recorded / Analyze: Movement over time, slope, aspect, rainfall build-up / Risk and explain: Lorem ipsum dolor sit amet, sed do eiusmod tempor incididunt ut labore. (placeholder, kept) / Dashboard: Interactive map and charts

### Part 3: The proof

#### Slide 05 - Space data

- **Audience move**: Wonders what it is built on → can name the NASA datasets behind it
- **Relationships**: membership: five sources belong to one data foundation
- **Composition**: Table takes the right two thirds; title and the placeholder line sit left in open space
- **Title**: Space data
- **Core message**: Built on NASA data.
- **Content**: Table Source | What it gives us: NISAR (L-band radar) | Ground displacement; 12-day repeat · NASADEM | Elevation, slope, aspect · GPM IMERG | Rainfall · SMAP | Soil moisture · NASA Global Landslide Catalog | Past landslides / Lorem ipsum: area covered, number of scenes, date range. (placeholder, kept; to fill with real figures)
- **Visualization**: nasa-sources — table/record_table, two columns, five rows
- **Native-ready**: nasa-sources=yes

#### Slide 06 - Impact

- **Audience move**: Understands the mechanism → sees what it delivers and that it is reusable
- **Relationships**: three parallel outcomes: result for the test area (placeholder); accuracy or validation (placeholder); open and reusable
- **Composition**: Takeaway line across the top; three statements side by side separated by hairlines, the two placeholders quieter, the third in ink; one amber seal marks the to-fill pair
- **Title**: Impact
- **Core message**: Open NASA data in, one usable map out.
- **Content**: Lorem ipsum dolor sit amet, consectetur adipiscing elit. (result for the test area) · Ut enim ad minim veniam, quis nostrud exercitation. (accuracy or validation) · Open NASA data in, one usable map out. Any region NISAR covers can reuse it.

### Part 4: What comes next

#### Slide 07 - Next steps

- **Audience move**: Believes it works in principle → sees a realistic path to scale
- **Relationships**: order of three phases: Phase A United States → Phase B Azerbaijan → later placeholder phase; B depends on A proving the pipeline
- **Composition**: A rising brush stroke from lower-left to upper-right with three phase marks on it; large numerals 1 2 3
- **Title**: Next steps
- **Core message**: Prove it where the data is lighter, then bring it to Azerbaijan.
- **Content**: 1 Phase A, United States: Lighter data and a well-documented landslide history / 2 Phase B, Azerbaijan: Terabytes of raw radar data, so it comes after the pipeline is proven / 3 Lorem ipsum: live public dashboard and the later model upgrades. (placeholder, kept)

#### Slide 08 - Team

- **Audience move**: Knows the product → knows who built it
- **Relationships**: membership: four people in one team, each with one role
- **Composition**: Four names in a row floating above the low horizon wash, role beneath each, initials as quiet ink marks
- **Title**: Team
- **Core message**: A small team covering engineering, design and AI.
- **Content**: Kanan Salmanli, Full Stack Developer · Sema Abdullazade, UI/UX Designer · Intiqam, Frontend Designer · Farid Gahramanov, AI Engineer

#### Slide 09 - Thank you

- **Audience move**: Convinced → scans the code and tries the app
- **Relationships**: none
- **Composition**: Cover's ridge sweep returns; QR frame sits where the seal sat, in amber outline; Thank you large on the left
- **Closing impact**: Takeaway (binding): scan the QR code to try the app. The QR is a labelled native frame until the app URL exists.
- **Title**: Thank you
- **Core message**: Thank you. Scan to try the app.
- **Content**: [QR code to the app] labelled frame / Thank you. / PRECURSOR AI

## X. Speaker Notes Requirements

- **Generation**: enabled
- **Filename**: match each SVG filename under `notes/`
- **Content**: Grounded in each final page; wording follows the previous deck's notes where the page content is unchanged; placeholders are named as to be filled before the pitch
- **Total duration**: about 3 minutes
- **Notes style**: conversational
- **Presentation purpose**: Explain the problem and how the platform works first; then persuade the judges that PRECURSOR AI is a credible, reusable use of NASA radar data for the "Dancing with the SARs" challenge.
