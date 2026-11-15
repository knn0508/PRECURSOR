<!-- ppt-master-schema: spec-lock/v1 -->
# Execution Lock

## canvas
- viewBox: 0 0 1280 720
- format: PPT 16:9

## communication
- primary_language: en
- audience: NASA Space Apps Challenge judges and attendees; technical, short on time, not InSAR specialists
- objective: Explain the problem and the platform, then persuade judges it is a credible, reusable use of NASA radar data, so they can state what it does in one sentence and scan the QR code
- core_message: Open NASA data in, one usable landslide early-warning map out; PRECURSOR AI sees landslides before they happen, from space
- consumption_mode: balanced

## mode
- mode: custom
- mode_references: narrative
- mode_behavior: Narrative arc over the fixed nine-slide order: unseen warning sign, data nobody can reach, one platform and its pipeline, NASA data and impact, phased roadmap, team and a scan-the-QR close. Plan slide titles stay as kickers; one short beat line per page advances the story. Lorem ipsum placeholders stay visible and are marked as to-fill.

## visual_style
- visual_style: ink-wash

## colors
- background: #0B1426
- secondary_bg: #14213D
- primary: #2DD4BF
- accent: #F2994A
- secondary_accent: #5B8DEF
- body_text: #F4F6FA
- secondary_text: #9AA8C2
- divider: #2A3A5C

## typography
- font_family: "Segoe UI", sans-serif
- title_family: "Segoe UI", sans-serif
- body_family: "Segoe UI", sans-serif
- label_family: Consolas, monospace
- body: 24
- title: 42
- subtitle: 32
- annotation: 18
- label: 16
- display: 84
- numeral: 56
- lead: 28

## icons
- library: phosphor-duotone
- inventory: phosphor-duotone/warning, phosphor-duotone/cell-signal-slash, phosphor-duotone/hard-drives, phosphor-duotone/cursor-click, phosphor-duotone/download-simple, phosphor-duotone/wave-sine, phosphor-duotone/stack, phosphor-duotone/gauge, phosphor-duotone/map-trifold, phosphor-duotone/planet, phosphor-duotone/mountains, phosphor-duotone/cloud-rain, phosphor-duotone/drop-half, phosphor-duotone/clock-counter-clockwise, phosphor-duotone/chart-line-up, phosphor-duotone/seal-check, phosphor-duotone/globe-hemisphere-east, phosphor-duotone/rocket-launch, phosphor-duotone/presentation-chart, phosphor-duotone/code, phosphor-duotone/paint-brush, phosphor-duotone/layout, phosphor-duotone/brain, phosphor-duotone/qr-code, phosphor-duotone/magnifying-glass, phosphor-duotone/eye-slash, phosphor-duotone/broadcast, phosphor-duotone/flag-banner

## page_rhythm
- P01: anchor
- P02: breathing
- P03: dense
- P04: dense
- P05: dense
- P06: breathing
- P07: dense
- P08: breathing
- P09: anchor

## page_visualizations
- P05: table/record_table

## pptx_structure
- mode: flat

## forbidden
- `mask`, `<style>`, `class`, external CSS, `<foreignObject>`, `textPath`, `@font-face`, `<animate*>`, `<set>`, `<script>` / event attributes, `<iframe>`
- HTML named entities in text; write typography as raw Unicode and escape XML reserved characters
