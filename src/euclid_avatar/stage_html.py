"""Full-bleed 16:9 (1920x1080) HTML/SVG/JS stage for `/avatar` and 1080p video rendering."""

from __future__ import annotations

AVATAR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Euclid of Alexandria · Elements II.13 (16:9 Full-Bleed Slide)</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background: #070a10;
    font-family: "Palatino Linotype", "Book Antiqua", Palatino, Georgia, serif;
    color: #fdfaf2;
    user-select: none;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  body.video-mode *, body.video-mode *::before, body.video-mode *::after {
    transition: none !important;
    animation: none !important;
  }
  /* Full-bleed 16:9 Google Presentation / Zoom HD stage (1920x1080 internal grid) */
  .stage-viewport {
    width: 1920px;
    height: 1080px;
    aspect-ratio: 16 / 9;
    position: relative;
    transform-origin: center center;
    background: radial-gradient(circle at 28% 42%, #1c2536 0%, #0d121c 68%, #070a10 100%);
    display: flex;
    flex-direction: column;
    justify-content: stretch;
    padding: 12px 14px;
    overflow: hidden;
  }
  .main-row {
    width: 100%;
    height: 1056px;
    display: grid;
    grid-template-columns: 768px 1fr;
    gap: 14px;
    align-items: stretch;
  }
  .diagram-card {
    position: relative;
    width: 768px;
    height: 1056px;
    background: rgba(11, 16, 26, 0.95);
    border: 2px solid rgba(229, 196, 103, 0.58);
    border-radius: 20px;
    padding: 18px 22px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: 0 14px 44px rgba(0, 0, 0, 0.75);
  }
  .diagram-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1.5px solid rgba(229, 196, 103, 0.34);
    padding-bottom: 10px;
    flex-shrink: 0;
  }
  .diagram-title {
    font-size: 27px;
    font-weight: 700;
    color: #f3d47c;
    letter-spacing: 0.02em;
  }
  .diagram-sub {
    font-size: 16px;
    color: #b0bed9;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin-top: 3px;
  }
  svg.ii13-fig {
    width: 100%;
    height: 724px;
    overflow: visible;
    flex-shrink: 0;
  }
  .geo-area {
    opacity: 0.16;
    transition: opacity 0.28s cubic-bezier(0.22, 1, 0.36, 1), filter 0.28s ease, transform 0.28s ease;
    transform-box: fill-box;
    transform-origin: center;
  }
  .geo-area.active-area {
    opacity: 0.96;
    filter: drop-shadow(0 0 16px rgba(243, 212, 124, 0.58));
    transform: scale(1.015);
  }
  .seg-line {
    transition: stroke-width 0.2s ease, filter 0.2s ease, opacity 0.2s ease;
  }
  .seg-line.active-glow {
    stroke-width: 7.5px !important;
    filter: drop-shadow(0 0 14px rgba(243, 212, 124, 0.98));
  }
  .pt-node {
    transition: transform 0.2s ease, filter 0.2s ease;
    transform-box: fill-box;
    transform-origin: center;
  }
  .pt-node.active-pt {
    filter: drop-shadow(0 0 14px rgba(243, 212, 124, 1));
    transform: scale(1.22);
  }
  @keyframes pulseAngle {
    0%, 100% { transform: scale(1); opacity: 0.85; }
    50% { transform: scale(1.12); opacity: 1; }
  }
  .angle-arc-active {
    animation: pulseAngle 1.4s ease-in-out infinite;
    filter: drop-shadow(0 0 10px rgba(243, 212, 124, 0.9));
  }
  .cue-banner {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 18px;
    font-weight: 700;
    color: #fff3c4;
    background: linear-gradient(90deg, rgba(229, 196, 103, 0.24) 0%, rgba(56, 139, 253, 0.2) 100%);
    border: 1.5px solid rgba(243, 212, 124, 0.6);
    border-radius: 12px;
    padding: 12px 16px;
    text-align: center;
    letter-spacing: 0.01em;
    transition: all 0.22s ease;
    flex-shrink: 0;
  }
  .case-legend {
    display: flex;
    flex-direction: column;
    gap: 8px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 16.5px;
    background: rgba(18, 26, 42, 0.88);
    border: 1px solid rgba(229, 196, 103, 0.32);
    border-radius: 14px;
    padding: 12px 16px;
    flex-shrink: 0;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 10px;
    color: #dce5f5;
    padding: 5px 8px;
    border-radius: 6px;
    border-left: 4px solid transparent;
    transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
  }
  .legend-item.active-leg {
    background: rgba(243, 212, 124, 0.18);
    border-left-color: #f3d47c;
    color: #ffffff;
    transform: translateX(4px);
  }
  .legend-swatch {
    width: 15px;
    height: 15px;
    border-radius: 3px;
    display: inline-block;
    flex-shrink: 0;
  }
  .slide-card {
    height: 1056px;
    background: rgba(11, 16, 26, 0.94);
    border: 2px solid rgba(229, 196, 103, 0.58);
    border-radius: 20px;
    padding: 22px 30px 18px 30px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: 0 14px 44px rgba(0, 0, 0, 0.75);
    overflow: hidden;
  }
  .slide-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1.5px solid rgba(229, 196, 103, 0.38);
    padding-bottom: 14px;
    margin-bottom: 16px;
    flex-shrink: 0;
  }
  .slide-title {
    font-size: 40px;
    font-weight: 700;
    color: #f3d47c;
    letter-spacing: 0.01em;
  }
  .slide-pill {
    background: #1b263b;
    border: 1.5px solid #e5c467;
    color: #f0d078;
    padding: 7px 20px;
    border-radius: 999px;
    font-size: 18.5px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-weight: 700;
    white-space: nowrap;
  }
  .slide-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: space-evenly;
    gap: 16px;
    min-height: 0;
  }
  .slide-row {
    background: rgba(23, 33, 52, 0.76);
    border-left: 5px solid rgba(229, 196, 103, 0.58);
    border-radius: 14px;
    padding: 20px 26px;
    transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
  }
  .slide-row.active-row {
    background: rgba(40, 58, 90, 0.94);
    border-left: 7px solid #f3d47c;
    box-shadow: 0 0 24px rgba(243, 212, 124, 0.25);
    transform: translateX(4px);
  }
  .slide-row-greek {
    font-family: "New Athena Unicode", "Gentium Plus", "Palatino Linotype", Georgia, serif;
    font-size: 32px;
    line-height: 1.46;
    color: #f7df94;
    margin-bottom: 9px;
  }
  .slide-row-eng {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 25px;
    line-height: 1.42;
    color: #e8effa;
  }
  /* Layout-specific scaling to maximize slide real estate per slide */
  .slide-body.layout-table_single .slide-row {
    padding: 36px 36px;
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .slide-body.layout-table_single .slide-row-greek {
    font-size: 39px;
    line-height: 1.54;
    margin-bottom: 28px;
  }
  .slide-body.layout-table_single .slide-row-eng {
    font-size: 30.5px;
    line-height: 1.5;
  }
  .slide-body.layout-table_rows .slide-row {
    padding: 22px 28px;
  }
  .slide-body.layout-table_rows .slide-row-greek {
    font-size: 35px;
    line-height: 1.42;
  }
  .slide-body.layout-table_rows .slide-row-eng {
    font-size: 26px;
  }
  .slide-body.layout-bullets-s4 .slide-row {
    padding: 22px 28px;
  }
  .slide-body.layout-bullets-s4 .slide-row-greek {
    font-size: 34px;
    line-height: 1.42;
  }
  .slide-body.layout-bullets-s4 .slide-row-eng {
    font-size: 25.5px;
  }
  .slide-body.layout-bullets-s5 .slide-row {
    padding: 19px 24px;
  }
  .slide-body.layout-bullets-s5 .slide-row-greek {
    font-size: 30px;
    line-height: 1.42;
  }
  .slide-body.layout-bullets-s5 .slide-row-eng {
    font-size: 23.5px;
    line-height: 1.38;
  }
  .slide-two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    align-items: center;
  }
  /* Single-word sequential highlight tokens */
  .w-tok {
    display: inline-block;
    border-radius: 6px;
    padding: 0 4px;
    margin: 0 -1px;
    transition: background 0.1s ease, color 0.1s ease, transform 0.1s ease, box-shadow 0.1s ease;
  }
  .w-tok.greek-tok.speaking {
    background: linear-gradient(180deg, rgba(243, 212, 124, 0.56) 0%, rgba(212, 160, 48, 0.48) 100%);
    color: #ffffff !important;
    font-weight: 700;
    transform: scale(1.07) translateY(-1px);
    box-shadow: 0 0 18px rgba(243, 212, 124, 0.9);
    border-bottom: 3px solid #ffd97d;
  }
  .w-tok.greek-tok.spoken {
    color: #fff6d6;
    border-bottom: 1.5px solid rgba(243, 212, 124, 0.38);
  }
  .w-tok.eng-tok.speaking {
    background: rgba(88, 166, 255, 0.42);
    color: #ffe58f !important;
    transform: scale(1.05);
    box-shadow: 0 0 14px rgba(88, 166, 255, 0.65);
    border-bottom: 2.5px solid #79c0ff;
  }
  .w-tok.eng-tok.spoken {
    color: #d8e8ff;
  }
  .pres-progress-wrap {
    width: 100%;
    height: 6px;
    background: rgba(27, 38, 59, 0.85);
    border-radius: 999px;
    overflow: hidden;
    margin-top: 12px;
    flex-shrink: 0;
  }
  .pres-progress-fill {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, #e5c467 0%, #58a6ff 100%);
  }
</style>
</head>
<body>
  <div class="stage-viewport" id="stageViewport">
    <div class="main-row">
      <div class="diagram-card">
        <div class="diagram-header">
          <div>
            <div class="diagram-title">Elements II.13 · Geometric Figure</div>
            <div class="diagram-sub">ΑΓ² = ΓΒ² + ΒΑ² − 2·ΓΒ·ΒΔ (Acute ∠Β, Altitude ΑΔ ⊥ ΓΒ)</div>
          </div>
          <div class="slide-pill" id="activeLettersBadge" style="font-size:16.5px;padding:6px 16px;">△ ΑΒΓ</div>
        </div>

        <svg class="ii13-fig" viewBox="8 -2 452 384" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="nomGoldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="rgba(243, 212, 124, 0.44)"/>
              <stop offset="100%" stop-color="rgba(218, 165, 32, 0.16)"/>
            </linearGradient>
            <linearGradient id="genBlueGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="rgba(88, 166, 255, 0.4)"/>
              <stop offset="100%" stop-color="rgba(56, 139, 253, 0.14)"/>
            </linearGradient>
            <linearGradient id="datGreenGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stop-color="rgba(86, 211, 100, 0.44)"/>
              <stop offset="100%" stop-color="rgba(46, 160, 67, 0.16)"/>
            </linearGradient>
            <linearGradient id="triAbdGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="rgba(210, 153, 34, 0.5)"/>
              <stop offset="100%" stop-color="rgba(210, 153, 34, 0.16)"/>
            </linearGradient>
            <linearGradient id="triAdcGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="rgba(163, 113, 247, 0.48)"/>
              <stop offset="100%" stop-color="rgba(163, 113, 247, 0.16)"/>
            </linearGradient>
          </defs>

          <!-- 1. GENITIVE SQUARE ON BA (□ ΒΑ², top-left outward polygon) -->
          <g id="grp-sq-BA" class="geo-area">
            <polygon points="100,248 184,104 102,56 18,200"
                     fill="url(#genBlueGrad)" stroke="#79c0ff" stroke-width="2.4" stroke-dasharray="6 3"/>
            <text x="98" y="132" text-anchor="middle" fill="#a5d6ff" font-size="14.5" font-weight="700">□ ΒΑ²</text>
            <text x="98" y="150" text-anchor="middle" fill="#79c0ff" font-size="12.5">ἀπὸ τῆς ΒΑ</text>
          </g>

          <!-- 2. NOMINATIVE SQUARE ON AC (□ ΑΓ², top-right outward polygon) -->
          <g id="grp-sq-AC" class="geo-area">
            <polygon points="184,104 376,248 448,152 256,8"
                     fill="url(#nomGoldGrad)" stroke="#f3d47c" stroke-width="2.6"/>
            <text x="318" y="114" text-anchor="middle" fill="#ffe58f" font-size="16" font-weight="700">□ ΑΓ² (Nom.)</text>
            <text x="318" y="134" text-anchor="middle" fill="#f3d47c" font-size="13.5">τὸ ἀπὸ τῆς ΑΓ</text>
          </g>

          <!-- 3. GENITIVE SQUARE ON CB (□ ΓΒ², subtle reference frame below base) -->
          <g id="grp-sq-CB" class="geo-area">
            <rect x="100" y="248" width="276" height="126" rx="4"
                  fill="url(#genBlueGrad)" stroke="#79c0ff" stroke-width="2.3" stroke-dasharray="7 4"/>
            <text x="316" y="365" text-anchor="middle" fill="#a5d6ff" font-size="14" font-weight="700">□ ΓΒ² (ἀπὸ τῆς ΓΒ)</text>
          </g>

          <!-- 4. DATIVE DOUBLE-RECTANGLE 2 · rect(ΓΒ, ΒΔ) below base ΓΒ -->
          <g id="grp-rect-2CBBD" class="geo-area">
            <rect id="rect-CB-BD" x="100" y="252" width="276" height="84" rx="5"
                  fill="url(#datGreenGrad)" stroke="#56d364" stroke-width="2.6"/>
            <line x1="100" y1="294" x2="376" y2="294" stroke="#56d364" stroke-width="1.7" stroke-dasharray="5 4"/>
            <line x1="184" y1="252" x2="184" y2="336" stroke="rgba(86, 211, 100, 0.75)" stroke-width="1.9" stroke-dasharray="4 3"/>
            <text x="242" y="280" text-anchor="middle" fill="#aff5b4" font-size="14.5" font-weight="700">
              1× ὑπὸ τῶν ΓΒ, ΒΔ (CB · BD)
            </text>
            <text x="242" y="320" text-anchor="middle" fill="#aff5b4" font-size="14.5" font-weight="700">
              2× τῷ δὶς ὑπὸ τῶν ΓΒ, ΒΔ (Dat.)
            </text>
          </g>

          <!-- 5. Base Triangle △ΑΒΓ interior & Slide 5 I.47 Right-Triangle Sub-Regions -->
          <polygon id="tri-ABC-base" points="184,104 100,248 376,248" fill="rgba(56, 139, 253, 0.09)"/>
          <polygon id="grp-tri-ABD" class="geo-area" points="184,104 100,248 184,248" fill="url(#triAbdGrad)" stroke="#f0b72f" stroke-width="2.2"/>
          <polygon id="grp-tri-ADC" class="geo-area" points="184,104 184,248 376,248" fill="url(#triAdcGrad)" stroke="#bc8cff" stroke-width="2.2"/>

          <!-- 6. Acute angle arc at Β (100, 248) -->
          <g id="grp-acute-B">
            <path d="M 138,248 A 38,38 0 0,0 119,215" fill="none" stroke="#f3d47c" stroke-width="2.9"/>
            <text x="144" y="236" fill="#f3d47c" font-size="14" font-weight="600" font-style="italic">ὀξεῖα</text>
          </g>

          <!-- 7. Right-angle marker at Δ (184, 248) -->
          <g id="grp-right-D">
            <polyline points="184,230 202,230 202,248" fill="none" stroke="#56d364" stroke-width="2.5"/>
          </g>

          <!-- 8. Primary Triangle Segments & Altitude -->
          <line id="seg-CB" class="seg-line" x1="100" y1="248" x2="376" y2="248" stroke="#79c0ff" stroke-width="4.6" stroke-linecap="round"/>
          <line id="seg-BD" class="seg-line" x1="100" y1="248" x2="184" y2="248" stroke="#56d364" stroke-width="5.6" stroke-linecap="round"/>
          <line id="seg-DC" class="seg-line" x1="184" y1="248" x2="376" y2="248" stroke="#79c0ff" stroke-width="4.6" stroke-linecap="round"/>
          <line id="seg-BA" class="seg-line" x1="100" y1="248" x2="184" y2="104" stroke="#79c0ff" stroke-width="4.6" stroke-linecap="round"/>
          <line id="seg-AC" class="seg-line" x1="184" y1="104" x2="376" y2="248" stroke="#f3d47c" stroke-width="5.4" stroke-linecap="round"/>
          <line id="seg-AD" class="seg-line" x1="184" y1="104" x2="184" y2="248" stroke="#56d364" stroke-width="4.0" stroke-dasharray="7 5" stroke-linecap="round"/>

          <!-- Segment Labels -->
          <text x="122" y="172" fill="#a5d6ff" font-size="15.5" font-weight="700">ΒΑ</text>
          <text x="292" y="170" fill="#f7df94" font-size="16.5" font-weight="700">ΑΓ</text>
          <text x="193" y="188" fill="#7ee787" font-size="14.5" font-weight="700">ἡ κάθετος ΑΔ</text>
          <text x="142" y="268" text-anchor="middle" fill="#7ee787" font-size="15" font-weight="700">ΒΔ (BD)</text>
          <text x="280" y="268" text-anchor="middle" fill="#a5d6ff" font-size="15" font-weight="700">ΔΓ (DC)</text>

          <!-- Inequality Hinge Badge (ἔλαττόν ἐστι) -->
          <g id="grp-hinge" class="geo-area">
            <rect x="190" y="40" width="142" height="33" rx="16.5" fill="#1b263b" stroke="#f3d47c" stroke-width="2.2"/>
            <text x="261" y="62" text-anchor="middle" fill="#ffe58f" font-size="15" font-weight="700">ἔλαττόν ἐστι (&lt;)</text>
          </g>

          <!-- Vertex Α (A) -->
          <g id="pt-A" class="pt-node">
            <circle cx="184" cy="104" r="15.5" fill="#172236" stroke="#f3d47c" stroke-width="2.6"/>
            <text x="184" y="110" text-anchor="middle" fill="#ffffff" font-size="17.5" font-weight="700">Α</text>
            <text x="184" y="79" text-anchor="middle" fill="#b7c2d6" font-size="13.5" font-family="-apple-system,sans-serif">A</text>
          </g>

          <!-- Vertex Β (B) -->
          <g id="pt-B" class="pt-node">
            <circle cx="100" cy="248" r="15.5" fill="#172236" stroke="#79c0ff" stroke-width="2.6"/>
            <text x="100" y="254" text-anchor="middle" fill="#ffffff" font-size="17.5" font-weight="700">Β</text>
            <text x="72" y="253" text-anchor="middle" fill="#b7c2d6" font-size="13.5" font-family="-apple-system,sans-serif">B</text>
          </g>

          <!-- Vertex Γ (C) -->
          <g id="pt-C" class="pt-node">
            <circle cx="376" cy="248" r="15.5" fill="#172236" stroke="#f3d47c" stroke-width="2.6"/>
            <text x="376" y="254" text-anchor="middle" fill="#ffffff" font-size="17.5" font-weight="700">Γ</text>
            <text x="404" y="253" text-anchor="middle" fill="#b7c2d6" font-size="13.5" font-family="-apple-system,sans-serif">C</text>
          </g>

          <!-- Point Δ (D) -->
          <g id="pt-D" class="pt-node">
            <circle cx="184" cy="248" r="14.5" fill="#172236" stroke="#56d364" stroke-width="2.6"/>
            <text x="184" y="254" text-anchor="middle" fill="#ffffff" font-size="16.5" font-weight="700">Δ</text>
          </g>
        </svg>

        <div class="cue-banner" id="figActiveCueLabel">
          PROPOSITION II.13 · Acute-Angled Triangle △ΑΒΓ with Altitude ΑΔ
        </div>

        <div class="case-legend">
          <div class="legend-item" id="leg-nom">
            <span class="legend-swatch" style="background:#f3d47c;"></span>
            <span><strong>Nom. (Subject):</strong> τὸ ἀπὸ τῆς ΑΓ — <em>square on AC (□ ΑΓ²)</em></span>
          </div>
          <div class="legend-item" id="leg-gen">
            <span class="legend-swatch" style="background:#79c0ff;"></span>
            <span><strong>Gen. ("than"):</strong> τῶν ἀπὸ τῶν ΓΒ, ΒΑ — <em>squares on CB, BA</em></span>
          </div>
          <div class="legend-item" id="leg-dat">
            <span class="legend-swatch" style="background:#56d364;"></span>
            <span><strong>Dat. ("by"):</strong> τῷ δὶς ὑπὸ τῶν ΓΒ, ΒΔ — <em>2 · rect(CB, BD)</em></span>
          </div>
        </div>
      </div>

      <div class="slide-card">
        <div class="slide-top">
          <div class="slide-title" id="slideTitle">II.13: the enunciation</div>
          <div class="slide-pill" id="slideBadge">Slide 1 / 5</div>
        </div>
        <div class="slide-body" id="slideBody"></div>
        <div class="pres-progress-wrap">
          <div class="pres-progress-fill" id="presProgressFill"></div>
        </div>
      </div>
    </div>
  </div>

<script>
  const stageViewport = document.getElementById('stageViewport');
  const slideTitle = document.getElementById('slideTitle');
  const slideBadge = document.getElementById('slideBadge');
  const slideBody = document.getElementById('slideBody');
  const activeLettersBadge = document.getElementById('activeLettersBadge');
  const figActiveCueLabel = document.getElementById('figActiveCueLabel');
  const presProgressFill = document.getElementById('presProgressFill');

  if (location.search.includes('video=1')) {
    document.body.classList.add('video-mode');
  }

  // Auto-scale 1920x1080 (16:9) stage to fit any browser window or OBS canvas cleanly
  function fitStageToWindow() {
    const vw = window.innerWidth || 1920;
    const vh = window.innerHeight || 1080;
    const sx = vw / 1920;
    const sy = vh / 1080;
    if (Math.abs((vw / vh) - (16 / 9)) < 0.11) {
      stageViewport.style.transform = `scale(${sx.toFixed(5)}, ${sy.toFixed(5)})`;
    } else {
      const scale = Math.min(sx, sy);
      stageViewport.style.transform = `scale(${scale.toFixed(5)})`;
    }
  }
  window.addEventListener('resize', fitStageToWindow);
  fitStageToWindow();

  function lockWindowTo16x9() {
    const targetW = Math.min(1600, Math.max(1280, window.innerWidth || 1440));
    const targetH = Math.round(targetW * 9 / 16);
    const chromeW = (window.outerWidth || targetW) - (window.innerWidth || targetW);
    const chromeH = (window.outerHeight || targetH) - (window.innerHeight || targetH);
    try {
      window.resizeTo(targetW + Math.max(0, chromeW), targetH + Math.max(0, chromeH));
    } catch (e) {}
    setTimeout(fitStageToWindow, 60);
  }
  if (location.search.includes('zoom16x9=1')) {
    setTimeout(lockWindowTo16x9, 80);
  }

  const ENG_STOPWORDS = new Set([
    'the','a','an','of','in','on','to','by','for','with','and','or','is','are',
    'it','that','this','from','at','as','be','one','two','all','up'
  ]);

  let currentSlideNumber = -1;
  let slideTokens = [];
  let wordToSlideIdx = [];
  let slideGreekCursor = 0;
  let slideEngCursor = 0;
  let currentSpeakingEl = null;
  let lastWordIdx = -1;

  function normalizeWordJS(str) {
    if (!str) return '';
    const trimmed = str.replace(/^[^\\w\\u0370-\\u03ff\\u1f00-\\u1fff]+|[^\\w\\u0370-\\u03ff\\u1f00-\\u1fff]+$/g, '');
    if (!trimmed) return '';
    return trimmed.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').normalize('NFC');
  }

  function isGreekToken(str) {
    return /[\\u0370-\\u03ff\\u1f00-\\u1fff]/.test(str || '');
  }

  function tokenizeHtmlWithSpans(rawText, defaultGreek) {
    if (!rawText) return '';
    const cleaned = rawText.replace(/\\*\\*(.+?)\\*\\*/g, '⟪B⟫$1⟪/B⟫').replace(/\\*(.+?)\\*/g, '⟪I⟫$1⟪/I⟫');
    const parts = cleaned.split(/(\\s+|⟪\\/?[BI]⟫)/);
    let out = '';
    for (const p of parts) {
      if (!p) continue;
      if (p === '⟪B⟫') { out += '<strong style="color:#fff;text-decoration:underline;text-decoration-color:#e5c467;">'; continue; }
      if (p === '⟪/B⟫') { out += '</strong>'; continue; }
      if (p === '⟪I⟫') { out += '<em style="color:#ffd97d;">'; continue; }
      if (p === '⟪/I⟫') { out += '</em>'; continue; }
      if (/^\\s+$/.test(p)) { out += p; continue; }
      const norm = normalizeWordJS(p);
      if (!norm) { out += p; continue; }
      const isGr = isGreekToken(p) || (defaultGreek && !/[A-Za-z]{2,}/.test(p));
      const cls = isGr ? 'w-tok greek-tok' : 'w-tok eng-tok';
      out += `<span class="${cls}" data-norm="${norm}">${p}</span>`;
    }
    return out;
  }

  function indexSlideTokens() {
    const els = Array.from(slideBody.querySelectorAll('.w-tok'));
    slideTokens = els.map((el, idx) => {
      el.dataset.tokIdx = String(idx);
      return {
        el,
        idx,
        norm: el.dataset.norm || '',
        isGreek: el.classList.contains('greek-tok'),
        rowEl: el.closest('.slide-row'),
      };
    });
  }

  function buildWordToSlideTokenMap(wordTimings, resetCursors) {
    wordToSlideIdx = new Array(wordTimings.length).fill(-1);
    if (!slideTokens.length || !wordTimings.length) return;

    const grToks = slideTokens.filter(t => t.isGreek);
    const enToks = slideTokens.filter(t => !t.isGreek);

    if (resetCursors || slideGreekCursor >= Math.max(1, grToks.length - 1)) {
      slideGreekCursor = 0;
    }
    if (resetCursors || slideEngCursor >= Math.max(1, enToks.length - 2)) {
      slideEngCursor = 0;
    }

    let prevEnMatched = false;
    let i = 0;
    const n = wordTimings.length;

    while (i < n) {
      const w = wordTimings[i];
      if (w.is_greek) {
        prevEnMatched = false;
        let j = i;
        while (j < n && wordTimings[j].is_greek) j++;
        const run = [];
        for (let k = i; k < j; k++) run.push(wordTimings[k].norm || '');

        let bestC = -1;
        let bestScore = -1e9;
        for (let c = 0; c < grToks.length; c++) {
          if (grToks[c].norm !== run[0]) continue;
          let mLen = 0;
          while (mLen < run.length && (c + mLen) < grToks.length) {
            if (grToks[c + mLen].norm === run[mLen]) mLen++;
            else break;
          }
          const dist = (c >= slideGreekCursor)
            ? (c - slideGreekCursor)
            : (grToks.length - slideGreekCursor + c + 5);
          const score = mLen * 100.0 - dist * 1.5;
          if (score > bestScore) {
            bestScore = score;
            bestC = c;
          }
        }
        if (bestC !== -1) {
          let cur = bestC;
          for (let k = i; k < j; k++) {
            const wn = wordTimings[k].norm || '';
            for (let look = cur; look < Math.min(grToks.length, cur + 3); look++) {
              if (grToks[look].norm === wn) {
                wordToSlideIdx[k] = grToks[look].idx;
                cur = look + 1;
                slideGreekCursor = cur;
                break;
              }
            }
          }
        }
        i = j;
      } else {
        const wn = w.norm || '';
        const nextWn = (i + 1 < n && !wordTimings[i + 1].is_greek) ? (wordTimings[i + 1].norm || '') : '';
        // Match spoken 2-letter geometric pairs ("A, C" -> "ac", "C, B" -> "cb", "B, D" -> "bd")
        if (wn.length === 1 && nextWn.length === 1) {
          const pairNorm = wn + nextWn;
          let pairMatched = -1;
          for (let off = 0; off < Math.min(enToks.length, 10); off++) {
            const c = slideEngCursor + off;
            if (c >= enToks.length) break;
            if (enToks[c].norm === pairNorm) {
              pairMatched = c;
              break;
            }
          }
          if (pairMatched !== -1) {
            wordToSlideIdx[i] = enToks[pairMatched].idx;
            wordToSlideIdx[i + 1] = enToks[pairMatched].idx;
            slideEngCursor = pairMatched + 1;
            prevEnMatched = true;
            i += 2;
            continue;
          }
        }
        let matched = -1;
        for (let off = 0; off < enToks.length; off++) {
          const c = slideEngCursor + off;
          if (c >= enToks.length) break;
          if (enToks[c].norm !== wn) continue;
          const adjCont = (off <= 1 && prevEnMatched);
          const twoWord = (nextWn && (c + 1) < enToks.length && enToks[c + 1].norm === nextWn);
          const distinctive = (wn.length >= 5 && !ENG_STOPWORDS.has(wn) && off <= 10);
          if (adjCont || twoWord || distinctive) {
            matched = c;
            break;
          }
        }
        if (matched !== -1) {
          wordToSlideIdx[i] = enToks[matched].idx;
          slideEngCursor = matched + 1;
          prevEnMatched = true;
        } else {
          prevEnMatched = false;
        }
        i++;
      }
    }
  }

  function applyDiagramCues(cues, bannerText) {
    const cueSet = new Set(cues || []);
    if (bannerText) {
      figActiveCueLabel.textContent = bannerText;
    }

    const setArea = (id, active) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('active-area', !!active);
    };
    const setSeg = (id, active) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('active-glow', !!active);
    };
    const setPt = (id, active) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('active-pt', !!active);
    };
    const setLeg = (id, active) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('active-leg', !!active);
    };

    const showNom = cueSet.has('sq_AC') || cueSet.has('all_equation');
    const showGen = cueSet.has('sq_CB_BA') || cueSet.has('all_equation');
    const showDat = cueSet.has('rect_2_CB_BD') || cueSet.has('all_equation') || cueSet.has('proof_ii7');

    setArea('grp-sq-AC', showNom);
    setArea('grp-sq-BA', showGen);
    setArea('grp-sq-CB', showGen || cueSet.has('proof_ii7'));
    setArea('grp-rect-2CBBD', showDat);
    setArea('grp-hinge', cueSet.has('hinge_less') || cueSet.has('all_equation'));
    setArea('grp-tri-ABD', cueSet.has('proof_i47_ABD'));
    setArea('grp-tri-ADC', cueSet.has('proof_i47_ADC'));

    setLeg('leg-nom', showNom);
    setLeg('leg-gen', showGen);
    setLeg('leg-dat', showDat);

    setSeg('seg-AC', showNom || cueSet.has('seg_AC') || cueSet.has('proof_i47_ADC'));
    setSeg('seg-CB', showGen || showDat || cueSet.has('seg_CB') || cueSet.has('proof_ii7'));
    setSeg('seg-BA', showGen || cueSet.has('seg_BA') || cueSet.has('proof_i47_ABD'));
    setSeg('seg-BD', showDat || cueSet.has('seg_BD') || cueSet.has('proof_ii7') || cueSet.has('proof_i47_ABD'));
    setSeg('seg-DC', cueSet.has('seg_DC') || cueSet.has('proof_ii7') || cueSet.has('proof_i47_ADC'));
    setSeg('seg-AD', cueSet.has('perp_AD') || cueSet.has('seg_AD') || cueSet.has('proof_i47_ABD') || cueSet.has('proof_i47_ADC'));

    setPt('pt-A', showNom || showGen || cueSet.has('perp_AD') || cueSet.has('proof_i47_ABD') || cueSet.has('proof_i47_ADC'));
    setPt('pt-B', showGen || showDat || cueSet.has('acute_triangle') || cueSet.has('seg_BD'));
    setPt('pt-C', showNom || showGen || showDat || cueSet.has('proof_ii7'));
    setPt('pt-D', cueSet.has('perp_AD') || cueSet.has('node_D') || cueSet.has('seg_BD') || cueSet.has('proof_ii7') || cueSet.has('proof_i47_ABD') || cueSet.has('proof_i47_ADC'));

    const acuteArc = document.getElementById('grp-acute-B');
    if (acuteArc) acuteArc.classList.toggle('angle-arc-active', cueSet.has('acute_triangle'));

    const activeBadgeParts = [];
    if (showNom) activeBadgeParts.push('□ ΑΓ²');
    if (showGen) activeBadgeParts.push('□ ΓΒ², ΒΑ²');
    if (showDat) activeBadgeParts.push('2·ΓΒ·ΒΔ');
    if (cueSet.has('perp_AD')) activeBadgeParts.push('ΑΔ ⊥ ΓΒ');
    if (cueSet.has('proof_i47_ABD')) activeBadgeParts.push('△ ΑΒΔ');
    if (cueSet.has('proof_i47_ADC')) activeBadgeParts.push('△ ΑΔΓ');
    activeLettersBadge.textContent = activeBadgeParts.length ? activeBadgeParts.join(' · ') : '△ ΑΒΓ';
  }

  function highlightActiveWord(wordIndex) {
    const targetIdx = wordToSlideIdx[wordIndex];
    if (typeof targetIdx !== 'number' || targetIdx < 0 || targetIdx >= slideTokens.length) {
      const nextTarget = (wordIndex + 1 < wordToSlideIdx.length) ? wordToSlideIdx[wordIndex + 1] : -1;
      if (currentSpeakingEl && nextTarget < 0) {
        currentSpeakingEl.classList.remove('speaking');
        currentSpeakingEl.classList.add('spoken');
        currentSpeakingEl = null;
      }
      return;
    }
    if (currentSpeakingEl && currentSpeakingEl !== slideTokens[targetIdx].el) {
      currentSpeakingEl.classList.remove('speaking');
      currentSpeakingEl.classList.add('spoken');
    }
    const tok = slideTokens[targetIdx];
    tok.el.classList.add('speaking');
    currentSpeakingEl = tok.el;
    if (tok.rowEl) {
      Array.from(slideBody.querySelectorAll('.slide-row')).forEach(r => {
        r.classList.toggle('active-row', r === tok.rowEl);
      });
    }
  }

  function clearWordHighlights() {
    if (currentSpeakingEl) {
      currentSpeakingEl.classList.remove('speaking');
      currentSpeakingEl = null;
    }
    document.querySelectorAll('.w-tok.speaking, .w-tok.spoken').forEach(el => {
      el.classList.remove('speaking', 'spoken');
    });
    document.querySelectorAll('.slide-row.active-row').forEach(el => {
      el.classList.remove('active-row');
    });
  }

  function renderSlideCard(pres) {
    if (!pres || !pres.active_slide) return;
    const s = pres.active_slide;
    const totalSlides = (pres.deck && pres.deck.total_slides) || 5;
    if (s.slide_number !== currentSlideNumber) {
      currentSlideNumber = s.slide_number;
      slideGreekCursor = 0;
      slideEngCursor = 0;
    }
    slideTitle.textContent = s.title;
    slideBadge.textContent = `Slide ${s.slide_number} / ${totalSlides}`;
    const layoutCls = s.layout === 'bullets' ? `layout-bullets-s${s.slide_number}` : `layout-${s.layout}`;
    slideBody.className = `slide-body ${layoutCls}`;

    let html = '';
    if (s.header) {
      html += `<div style="font-size:27px;color:#b8ccf0;font-weight:700;margin-bottom:2px;">${tokenizeHtmlWithSpans(s.header, true)}</div>`;
    }
    if (s.layout === 'table_two_col') {
      const h0 = (s.headers && s.headers[0]) || 'II.12, obtuse';
      const h1 = (s.headers && s.headers[1]) || 'II.13, acute';
      html += `<div class="slide-two-col" style="border-bottom:1.5px solid rgba(229,196,103,0.35);padding:4px 22px 10px 22px;font-size:26px;color:#b8ccf0;font-weight:700;"><div>${h0}</div><div>${h1}</div></div>`;
      (s.rows || []).forEach(r => {
        html += `<div class="slide-row slide-two-col" style="padding:18px 24px;"><div class="slide-row-greek" style="font-size:30px;margin:0;">${tokenizeHtmlWithSpans(r.greek, true)}</div><div class="slide-row-greek" style="font-size:30px;margin:0;color:#ffffff;">${tokenizeHtmlWithSpans(r.english, true)}</div></div>`;
      });
    } else {
      (s.rows || []).forEach(r => {
        html += `<div class="slide-row">
          <div class="slide-row-greek">${tokenizeHtmlWithSpans(r.greek, true)}</div>
          ${r.english ? `<div class="slide-row-eng">${tokenizeHtmlWithSpans(r.english, false)}</div>` : ''}
        </div>`;
      });
    }
    slideBody.innerHTML = html;
    indexSlideTokens();
  }

  // Deterministic state controller for offline 1080p video rendering
  window.prepareSlideForVideo = function(slideObj, totalSlides) {
    currentSlideNumber = -1;
    renderSlideCard({ active_slide: slideObj, deck: { total_slides: totalSlides || 5 } });
    clearWordHighlights();
    applyDiagramCues(['acute_triangle'], 'PROPOSITION II.13 · Acute-Angled Triangle △ΑΒΓ with Altitude ΑΔ');
  };

  window.prepareSegmentForVideo = function(wordTimings, resetCursors) {
    if (currentSpeakingEl) {
      currentSpeakingEl.classList.remove('speaking');
      currentSpeakingEl.classList.add('spoken');
      currentSpeakingEl = null;
    }
    if (resetCursors) {
      clearWordHighlights();
    }
    buildWordToSlideTokenMap(wordTimings || [], !!resetCursors);
    return wordToSlideIdx.slice();
  };

  window.stepVideoWord = function(wordIndex, diagramCues, cueBanner, progressPct) {
    if (typeof progressPct === 'number' && presProgressFill) {
      presProgressFill.style.width = `${Math.max(0, Math.min(100, progressPct)).toFixed(2)}%`;
    }
    if (diagramCues && diagramCues.length) {
      applyDiagramCues(diagramCues, cueBanner || '');
    }
    if (typeof wordIndex === 'number' && wordIndex >= 0) {
      highlightActiveWord(wordIndex);
    }
    const activeTokIdx = currentSpeakingEl ? Number(currentSpeakingEl.dataset.tokIdx || -1) : -1;
    const spokenCount = slideBody.querySelectorAll('.w-tok.spoken').length;
    return `${currentSlideNumber}|${activeTokIdx}|${spokenCount}|${(diagramCues || []).join(',')}|${cueBanner || ''}`;
  };

  function connectWS() {
    if (location.search.includes('video=1')) return;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'init') {
        if (msg.presentation) renderSlideCard(msg.presentation);
      } else if (msg.type === 'presentation_state') {
        renderSlideCard(msg.presentation);
      } else if (msg.type === 'amplitude') {
        if (msg.diagram_cues && msg.diagram_cues.length) {
          applyDiagramCues(msg.diagram_cues, msg.cue_banner || '');
        }
        if (typeof msg.word_index === 'number' && msg.word_index !== lastWordIdx) {
          lastWordIdx = msg.word_index;
          highlightActiveWord(msg.word_index);
        }
      } else if (msg.type === 'subtitle') {
        lastWordIdx = -1;
        const timings = msg.word_timings || [];
        buildWordToSlideTokenMap(timings, false);
        if (timings.length > 0 && timings[0].diagram_cues) {
          applyDiagramCues(timings[0].diagram_cues, timings[0].cue_banner || '');
        }
        if (!msg.speaking) {
          clearWordHighlights();
        }
      } else if (msg.type === 'turn_update' && msg.turn && msg.turn.status === 'speaking') {
        currentSlideNumber = -99;
        slideGreekCursor = 0;
        slideEngCursor = 0;
        slideTitle.textContent = 'Professor Q&A · Elements II.13';
        slideBadge.textContent = 'Live Q&A';
        slideBody.innerHTML = `<div class="slide-row active-row"><div class="slide-row-eng" style="color:#9aa8c2;margin-bottom:10px;">Question: ${msg.turn.transcript || ''}</div><div class="slide-row-greek">${tokenizeHtmlWithSpans(msg.turn.greek || '', true)}</div><div class="slide-row-eng" style="margin-top:10px;">${tokenizeHtmlWithSpans(msg.turn.english || '', false)}</div></div>`;
        indexSlideTokens();
      }
    };
    ws.onclose = () => setTimeout(connectWS, 1000);
  }
  function openZoomStage16x9() {
    window.open(
      '/avatar?zoom16x9=1',
      'EuclidZoomStage16x9',
      'popup=yes,width=1440,height=838,menubar=no,toolbar=no,location=no,status=no'
    );
  }

  connectWS();
</script>
</body>
</html>
"""
