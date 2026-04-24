# Desktop Card Viewer Design

Status: Phase 1 read-only desktop viewer implemented, with the first visual refinement pass applied.

Entry point:

```powershell
python scripts/kb_desktop.py --repo-root .
```

Headless check:

```powershell
python scripts/kb_desktop.py --repo-root . --check
```

## Objective

The human UI should be a local desktop window, not a browser page. The first version keeps the repository's core constraints:

- file-first
- path-first
- lightweight
- no vector database
- no browser, web server, Electron, Node, or remote service dependency

The UI is a viewer for humans to inspect the KB. The files remain the source of truth.

The first desktop UI should optimize for calm browsing, not for exposing every field at once.

The visual target is the generated concept mockup: white main background, soft off-white sidebar, a single red/pink accent for selection, and large cover-like cards as the primary objects. Avoid pink-tinted page backgrounds; the page foundation should read as white.

## Interaction Model

The design follows a music-library metaphor.

- The left side is the library navigation area.
- The route tree works like albums, artists, or playlists: different paths can surface the same card.
- The right side is the card deck.
- The selected route shows a cover-card grid, similar to browsing albums or playlists.
- Search should update the card deck as the user types, with Enter acting as an immediate search action rather than the only way to trigger search.
- Search should show only cards with route or lexical relevance. Confidence and trust status may rerank relevant cards, but they should not make unrelated cards appear by themselves.
- Card details open after a single explicit card click or Enter action.
- Left and right arrow keys move through the current deck.
- The detail window is a separate expanded-card surface with `If`, `Action`, `Predict`, `Use`, route metadata, and recent history when available.

## Layout

### Left Sidebar

The sidebar should stay simple:

- app identity
- search box
- a few stable shortcuts
- route tree

It should not contain card summaries, metrics, or maintenance reports. Its job is navigation only.

Stable shortcuts include broad library cuts such as all cards, trusted cards, candidate cards, and card-type filters such as model and preference. These are local deck filters, not separate storage paths.

The app identity should be legible at a glance. Keep the logo and `Khaos Brain` wordmark large enough to read at normal laptop scaling, and use a bold black wordmark so it belongs with the rest of the UI hierarchy.

Route section labels should align with the sidebar content edge and read as section headings, not muted metadata floating in the middle of the sidebar.

### Right Card Area

The right side should make one thing obvious: these are individual predictive model cards.

It contains:

- current route title
- card count
- current route path when browsing a branch
- cover-card grid

The main workspace should not show both a preview strip and a full selected-card detail at the same time. That creates a control-panel feeling and makes the UI visually noisy.

The default card cover should show only:

- status
- card type
- confidence when available
- title
- short prediction preview
- id

The title and short prediction preview are the primary readable content on a card cover. They should be visually comparable to the sidebar navigation labels; do not let formula-based width caps shrink them below the navigation text.

The detail surface belongs in a separate popup window so the browse screen stays simple. The expanded card header should reuse the same color family as the selected cover.

Implementation note: the Tkinter desktop UI should prefer custom canvas drawing for the main shell and card grid. Native Tk buttons, tree widgets, and scrollbars should not dominate the default view because they make the app look like a utility panel instead of a calm card library.

The card deck should adapt to the available desktop width. Wide screens can show up to five cover cards per row, while short decks should align the count and route metadata to the actual visible card group instead of reserving empty columns.

The left navigation should behave like a library sidebar: stable shortcuts first, then route branches with card counts, active route state, and ancestor state.

Sidebar typography and icons should use one local visual system. Avoid mixing Unicode symbol glyphs from different fallback fonts because they make the sidebar look inconsistent on Windows high-DPI screens. Route rows should use subtle hierarchy markers such as short branch lines, not checkbox-like squares. Active state should be expressed with accent color, a soft row surface, and the left accent rail rather than sudden black text or heavier font weight.

Route values remain English canonical paths in files and retrieval code. When the desktop UI is in Chinese, route segments should be translated in the display layer only, including the sidebar tree, route title/chip, and detail-window route metadata. Unknown or newly created route segments may fall back to the canonical English segment until sleep/i18n maintenance adds a display label.

## Visual QA Rule

UI work is not done when the code runs. For this project, visual QA is part of the implementation loop:

1. open the desktop UI
2. let the first render settle, then maximize the desktop window on the user's actual laptop/primary screen before judging the layout
3. keep a realistic minimum window size so a tiny startup frame cannot become the visual baseline
4. capture the real physical monitor after maximize; do not judge only from a large virtual frame or a guessed crop
5. open and inspect that screenshot before claiming the UI is fixed
6. compare it against the current visual target mockup
7. check for text clipping, overlap, crowding, harsh outlines, broken spacing, missing scroll affordances, and accidental control-panel feel
8. click each changed navigation shortcut, route branch, and footer control, then screenshot those states too
9. fix visible defects before treating the task as complete

This is especially important for Tkinter canvas UI because geometry can pass tests while still looking wrong at real window sizes.

For Tkinter canvas text, prefer negative font sizes so text is specified in pixels. Positive point sizes can scale unpredictably under Windows high-DPI/maximized screenshots and make card text overlap even when the layout math appears correct.

If the screenshot tool reports only a scaled quadrant of the screen, fix the screenshot method first. The QA baseline must represent the same full-screen view the user sees.

Card covers should use simple procedural gradients before a formal asset pipeline exists. Avoid decorative line-art overlays on top of card covers; those compete with the prediction text and make the cards feel crowded.

The card-cover palette should be richer than the app chrome. The app shell can stay neutral and restrained, but cards should feel more like collectible covers: multiple vivid families such as rose, orange, yellow, violet, blue, cyan, green, cranberry, and softened gray-blue. Avoid using near-black as the default candidate-card color; uncertain cards can be gray-blue or muted color, but should not visually read as a black error state.

Cards should use a horizontal cover ratio rather than near-square tiles. This better matches the Apple Music-style library metaphor and gives titles plus short prediction previews more room. Selection should not rely on a harsh red outline around the card. Use hover lift, a slightly larger card surface, and a deeper shadow for focus; single-click opens the detail surface.

On Windows high-DPI screens, the desktop viewer should declare DPI awareness before creating the Tk root. Otherwise Windows can bitmap-scale the whole app, making text and canvas artwork look blurry. After DPI awareness is enabled, apply a bounded UI scale inside the app so the interface stays readable without returning to blurry system scaling. The internal scale should still follow the user's Windows display scale closely enough that a 4K laptop using display magnification does not render tiny text.

When the user says the UI is still smaller than other native apps, diagnose before changing values. Compare the reported Windows DPI scale with the app's internal unit scale, internal font scale, and native design tokens. Treat these as separate levers: DPI-following controls overall physical size, while base tokens control the app's native density.

The sidebar footer controls should be fixed outside the scrollable route tree. If Settings/About live inside the scrolling canvas, they can be partially hidden or collide with route rows when the user scrolls to the bottom.

## Icon Assets

The desktop viewer uses the generated Khaos Brain card-stack icon from `assets/`:

- `khaos-brain-icon-source.png`: archived full generated source image
- `khaos-brain-icon.png`: cropped application icon
- `khaos-brain-icon-64.png`: sidebar brand mark

The intended reusable mark is the inner stack of three memory cards with a high-contrast white ring on the front card. Earlier brain-line variants were harder to read at small Windows icon sizes, so the ring is the current production mark. The outer generated glass frame is treated as source context, not as the UI brand mark.

Settings currently owns display language only. English card fields remain the canonical source, while `i18n.zh-CN` is an optional display layer filled by sleep maintenance. The UI should render Chinese when selected and fall back to English for any untranslated field.

Language controls should stay discoverable in every display language. The sidebar footer should label settings bilingually, and the settings dialog should use a clearly marked `Language / 语言` selector with a globe icon and bilingual options such as `English / 英文` and `中文 / Chinese`, rather than relying on tiny radio indicators.

## Multi-Route Behavior

Cards are not duplicated when they appear through different routes.

The data layer groups a selected route into:

- `primary`: cards whose `domain_path` belongs under the selected branch
- `cross`: cards whose `cross_index` makes them reachable from that branch

Both open the same card object.

## Technical Shape

The desktop app uses Python's standard `tkinter` library.

It reuses a small data adapter in `local_kb/ui_data.py`:

- `build_route_view_payload`
- `build_card_detail_payload`
- `build_search_payload`
- `build_overview_payload`

The desktop app should not reimplement retrieval, YAML loading, taxonomy counting, or scoring. It only renders existing file-based data into a human-facing view.

## Non-Goals For Phase 1

This first UI does not attempt to provide:

- inline editing
- proposal approval
- sleep/dream run controls
- a graph visualization
- a full maintenance console

Those can be added later if they remain local, auditable, and simple.
