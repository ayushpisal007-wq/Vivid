/** Everything here is meant to be said out loud. Numbers come from showcase.json, never typed in. */

export const PHOTO_NOTES = {
  sample_landscape: {
    pick: "hayao_v3",
    look: "Look at the sky and the rock. Hayao keeps the scene and turns texture into drawn lines. The Classic Filter draws black dashes across the clouds, because it can't tell a cloud edge from an outline.",
    but: "CartoonGAN changes the colours: the blue sky goes brown in CartoonGAN Hayao and green in CartoonGAN Hosoda and CartoonGAN Paprika. We checked our CartoonGAN Hayao and Hosoda against published sample outputs and they match, so this comes from the models, not from our code.",
  },
  sample_portrait: {
    pick: "face_paint_v2",
    look: "Look at the eyes and the skin. Portrait was trained on faces, so it redraws the eyes cleanly and brightens the skin. Hayao and Shinkai keep more of the photo and add drawn strokes.",
    but: "Paprika invents cracks on the bright side of the face. Portrait also changes the lighting: it lifts shadows that the photographer put there on purpose.",
  },
  sample_street: {
    pick: "cartoongan_hayao",
    look: "Look at the fur. The film styles turn it into shapes and lines that follow the head. The Classic Filter covers the lioness in spots, like a leopard, because to a fixed threshold every bit of fur is an edge.",
    but: "Cel Shade puts scribbles on the fur and pushes the shadows to black. It learned on faces, and this is not one.",
  },
};

export function averageNotes(rows) {
  const by = (id) => rows.find((r) => r.style.id === id);
  const filter = by("classic_filter");
  const ai = rows.filter((r) => r !== filter);
  const low = (key) => ai.reduce((a, b) => (b[key] < a[key] ? b : a));
  const high = (key) => ai.reduce((a, b) => (b[key] > a[key] ? b : a));
  return [
    {
      title: "How to read it",
      text: "SSIM asks: is the structure still there? 1 is identical. Hist shift asks: did the colours change? 0 is the same palette. Edge Δ asks: are there more or fewer edges? None of these means better or worse. A cartoon is supposed to change the photo.",
    },
    {
      title: "What it says",
      text: `${high("ssim").style.name} keeps the most structure (SSIM ${high("ssim").ssim.toFixed(2)}). ${low("hist").style.name} changes the colours least (${low("hist").hist.toFixed(2)}) and ${high("hist").style.name} changes them most (${high("hist").hist.toFixed(2)}).`
        + (filter ? ` The filter scores ${filter.ssim.toFixed(2)} on SSIM, below ${ai.filter((r) => r.ssim > filter.ssim).length} of the ${ai.length} AI styles: its black speckle damages structure too.` : ""),
    },
    {
      title: "What we would pick",
      text: "Hayao is the safest default: fast, stable colours, works on every photo here. For a face, Portrait. For a bold comic look, Cel Shade. CartoonGAN is the original idea and gives strong lines, but its colours can drift.",
    },
    {
      title: "Be careful with",
      text: "This is an average of a few photos, so it is a sanity check, not a benchmark. The portrait pulls Edge Δ up: it is so soft that it starts with almost no edges. CartoonGAN runs at 512 px, so its time is not comparable pixel for pixel.",
    },
  ];
  
}

export const LIMITS = {
  faces: {
    what: "Paprika draws cracks on smooth, bright skin. On a tiny 128 px face, Portrait sharpens eyes and brows that were never sharp in the photo, so the person changes a little.",
    why: "The models only know faces like the ones they were trained on. Close-ups, hard light and low resolution push them outside that. Training also rewards crisp lines, which is a likely reason for the cracks: it draws lines where there are none.",
  },
  detail: {
    what: "Portrait Classic turns a whole forest into brown haze. Cel Shade covers the leaves with a repeating dotted pattern.",
    why: "Cartoons are flat shapes with clean lines, so training rewards exactly that. Leaves, hair and fabric don't fit, so they get smeared or replaced by a pattern. It is a side effect of the goal, not a bug.",
  },
  flicker: {
    why: "The network sees one image at a time and has no memory of the last one. Fixing it needs training that compares neighbouring frames, which none of these models had.",
  },
};
