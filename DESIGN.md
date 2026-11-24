# Vivid: design spec

Inspired by an editorial photography-studio site (Okoro), adapted to Vivid.

- **Palette:** off-white paper #F4F3F0 background, ink #0E0E0E, grey #8A8A8A for secondary text, one accent used sparingly (warm vermilion #E5462E) for active states. Alternate with dark #111 sections in white text for rhythm.
- **Type:** a giant condensed bold wordmark "Vivid" (Anton or a similar condensed grotesk from Google Fonts) filling about 60% of the hero width. Headings and body in a clean grotesk (Inter Tight or Manrope), large and tightly tracked. Small uppercase letter-spaced nav labels. Monospace (JetBrains Mono) for frame numbers and metrics.
- **Signature motif, a film strip:** the hero has a gently wavy, slowly drifting film strip with sprocket holes and frame labels like "VIVID 400" and "05 ▸ 5A". Its frames are real cartoonized examples; hovering a frame flips between original and cartoon. Thin film-strip bands work as section dividers.
- **Nav:** condensed "Vivid" logo top-left; uppercase links top-right (STUDIO, STYLES, HOW IT WORKS, PORTFOLIO, LIMITS); a solid black "TRY IT" button; hamburger menu on mobile.
- **Hero:** wordmark on the left, one-line tagline on the right ("Photos into anime and cartoon art with pretrained GANs, compared honestly."), a small live-status dot bottom-left ("Models online · N styles", from /api/health).
- **Styles showcase:** full-bleed slideshow like a campaign viewer. Big cartoonized image, "01 / 0N" counter, huge white style name, subtitle (family and source), "TRY THIS STYLE" link, and a NEXT thumbnail card bottom-right.
- **Studio**, the core tool, laid out like a booking form: big heading "Make it Vivid" on the left. On the right: a drop zone (drag-drop, click, paste from clipboard, webcam capture), style selector as rectangular pill toggles (active = solid black), intensity slider, color-pop toggle, black "CARTOONIZE" button, plus "Try an example" and "Compare all styles" as outlined buttons.
- **Results:** a draggable before/after reveal slider, a metrics row in mono (SSIM / Hist shift / Edge Δ / ms), Download PNG, and a session-history strip drawn as a film strip (click to reload). An "AI vs Filter" toggle shows the same photo through the Classic Filter next to the GAN.
- **How it works:** 4 columns with hairline rules and mono step numbers (01 ▸ 01A … 04 ▸ 04A): Upload → Encode → Stylize (generator vs discriminator) → Compare. Below that, a clean SVG diagram of the generator (encoder → residual blocks → decoder), the discriminator, and the losses (adversarial, content/VGG, style, edge-promoting), plus a short note on unpaired image-to-image translation (photo domain ↔ cartoon domain, same family as CycleGAN).
- **Stats band** (big numbers, small captions): number of styles, real average inference time, max resolution, "0 paired training images needed".
- **Portfolio**, then **Limits** (faces, fine detail, temporal flicker) on a dark section with the failure-case images.
- **Jury Q&A section:** "How is this different from a photo filter?" and "Where does it break down?", short answers linking to the live AI-vs-Filter demo and the failure cases.
- **Motion:** subtle only (film strip drift, fade/slide-up on scroll, image cross-fades). Respect prefers-reduced-motion.
- **Buttons:** 4px radius, solid black primary, outlined secondary, clear hover and focus states. Loading state: a skeleton frame with a scanning line and the text "Developing your frame…".
- Fully responsive: must look great on a 1920px projector and on a phone.
