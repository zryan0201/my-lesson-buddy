/* Original mix-and-match artwork and drawing tools. No upload or server required. */
const INK = '#293650';
const TAU = Math.PI * 2;
const HEX = /^#[0-9a-f]{6}$/i;
const MOTIONS = new Set(['idle', 'wave', 'talk', 'celebrate', 'walk', 'point', 'carry', 'give', 'think']);
const TOOLS = new Set(['pen', 'eraser', 'line', 'rectangle', 'circle', 'fill']);
const MAX_PIXELS = 12_000_000;
const MAX_IMAGE_LENGTH = 12 * 1024 * 1024;
const drawingCache = new Map();
const drawingBoundsCache = new Map();

export const DEFAULT_DESIGN = Object.freeze({
  version: 1, name: 'Spark', body_type: 'kid', head_shape: 'round', eyes: 'friendly',
  headwear: 'none', chest: 'star', back: 'cape', gloves: 'none', boots: 'round',
  primary_color: '#647CDE', secondary_color: '#55C6BC', accent_color: '#FFD36E', skin_color: '#F4BE99',
});

const choices = {
  body_type: [['kid', 'Little hero'], ['robot', 'Robot'], ['creature', 'Creature']],
  head_shape: [['round', 'Round'], ['angular', 'Angular']],
  eyes: [['round', 'Bright eyes'], ['visor', 'Space visor'], ['friendly', 'Happy eyes']],
  headwear: [['none', 'No headwear'], ['web_mask', 'Web mask'], ['helmet', 'Explorer helmet'], ['ears', 'Creature ears'], ['antenna', 'Antenna']],
  chest: [['none', 'No badge'], ['star', 'Star'], ['bolt', 'Lightning'], ['gem', 'Crystal'], ['reactor', 'Power core']],
  back: [['none', 'No back piece'], ['cape', 'Cape'], ['wings', 'Wings']],
  gloves: [['none', 'Simple hands'], ['gauntlets', 'Power gloves']],
  boots: [['round', 'Round boots'], ['armored', 'Armor boots']],
};
export const OPTIONS = Object.freeze(Object.fromEntries(Object.entries(choices).map(([field, values]) =>
  [field, Object.freeze(values.map(([value, label]) => Object.freeze({ value, label })))])));

export function normalizeDesign(value = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Choose a character design.');
  if (Object.keys(value).some(key => !Object.hasOwn(DEFAULT_DESIGN, key))) throw new Error('This character contains an unknown part.');
  const design = { ...DEFAULT_DESIGN, ...value };
  if (design.version !== 1) throw new Error('This character version is not supported.');
  for (const [field, options] of Object.entries(OPTIONS)) {
    if (!options.some(option => option.value === design[field])) throw new Error(`Choose a supported ${field.replaceAll('_', ' ')}.`);
  }
  for (const field of ['primary_color', 'secondary_color', 'accent_color', 'skin_color']) {
    if (typeof design[field] !== 'string' || !HEX.test(design[field])) throw new Error('Choose a six-digit character color.');
    design[field] = design[field].toUpperCase();
  }
  if (typeof design.name !== 'string') throw new Error('Give your buddy a name.');
  const name = design.name.normalize('NFC').replace(/\p{Zs}/gu, ' ').trim().replace(/ +/g, ' ');
  if ([...name].length < 1 || [...name].length > 32 || !/[\p{L}\p{N}]/u.test(name) || /[^\p{L}\p{N}\p{M} '\u2019-]/u.test(name)) {
    throw new Error('Use 1–32 letters or numbers, spaces, apostrophes, or hyphens for the name.');
  }
  design.name = name;
  return design;
}

export const PRESETS = Object.freeze([
  { id: 'star_explorer', name: 'Star Explorer', design: { name: 'Nova', body_type: 'kid', head_shape: 'angular', headwear: 'helmet', chest: 'star', back: 'cape', gloves: 'gauntlets', boots: 'armored', primary_color: '#568ADA', secondary_color: '#EE7B7B', accent_color: '#FFD36E' } },
  { id: 'bolt_builder', name: 'Bolt Builder', design: { name: 'Bolt', body_type: 'robot', eyes: 'visor', headwear: 'antenna', chest: 'bolt', back: 'none', gloves: 'gauntlets', boots: 'armored', primary_color: '#F4AD64', secondary_color: '#54B6B5', accent_color: '#FFE390' } },
  { id: 'moon_fox', name: 'Moon Fox', design: { name: 'Luna', body_type: 'creature', eyes: 'round', headwear: 'ears', chest: 'gem', back: 'cape', primary_color: '#B49ADD', secondary_color: '#65BFB7', accent_color: '#F4B783' } },
  { id: 'wing_wonder', name: 'Wing Wonder', design: { name: 'Wisp', body_type: 'kid', headwear: 'web_mask', eyes: 'round', chest: 'reactor', back: 'wings', gloves: 'gauntlets', primary_color: '#D98BAB', secondary_color: '#6DC7CC', accent_color: '#FFDE8A', skin_color: '#A96E52' } },
].map(preset => Object.freeze({ ...preset, design: Object.freeze(normalizeDesign(preset.design)) })));

function light(color, amount = .4) {
  const rgb = color.match(/[0-9a-f]{2}/gi).map(value => parseInt(value, 16));
  return `rgb(${rgb.map(channel => Math.round(channel + (255 - channel) * amount)).join(',')})`;
}
function dark(color, amount = .16) {
  return `rgb(${color.match(/[0-9a-f]{2}/gi).map(value => Math.round(parseInt(value, 16) * (1 - amount))).join(',')})`;
}
function finish(ctx, fill, outline = INK, width = 5) {
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (outline && width > 0) { ctx.strokeStyle = outline; ctx.lineWidth = width; ctx.stroke(); }
}
function ellipse(ctx, box, fill, outline = INK, width = 5) {
  ctx.beginPath(); ctx.ellipse((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, (box[2] - box[0]) / 2, (box[3] - box[1]) / 2, 0, 0, TAU);
  finish(ctx, fill, outline, width);
}
function round(ctx, box, radius, fill, outline = INK, width = 5) {
  const [x, y, endX, endY] = box;
  const r = Math.max(0, Math.min(radius, (endX - x) / 2, (endY - y) / 2));
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(endX - r, y); ctx.quadraticCurveTo(endX, y, endX, y + r);
  ctx.lineTo(endX, endY - r); ctx.quadraticCurveTo(endX, endY, endX - r, endY);
  ctx.lineTo(x + r, endY); ctx.quadraticCurveTo(x, endY, x, endY - r);
  ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath(); finish(ctx, fill, outline, width);
}
function polygon(ctx, points, fill, outline = INK, width = 5) {
  ctx.beginPath(); ctx.moveTo(...points[0]); points.slice(1).forEach(point => ctx.lineTo(...point)); ctx.closePath(); finish(ctx, fill, outline, width);
}
function line(ctx, points, color = INK, width = 5) {
  ctx.beginPath(); ctx.moveTo(...points[0]); points.slice(1).forEach(point => ctx.lineTo(...point)); finish(ctx, null, color, width);
}
function arc(ctx, box, start, end, color = INK, width = 5) {
  ctx.beginPath(); ctx.ellipse((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, (box[2] - box[0]) / 2, (box[3] - box[1]) / 2, 0, start * Math.PI / 180, end * Math.PI / 180); finish(ctx, null, color, width);
}
function pill(ctx, points, color, width) {
  line(ctx, points, INK, width + 10); line(ctx, points, color, width);
}
function curve(start, control1, control2, end) {
  return Array.from({ length: 21 }, (_, index) => {
    const t = index / 20, u = 1 - t;
    return [0, 1].map(axis => u ** 3 * start[axis] + 3 * u ** 2 * t * control1[axis] + 3 * u * t ** 2 * control2[axis] + t ** 3 * end[axis]);
  });
}
const mirror = points => points.map(([x, y]) => [600 - x, y]);

function back(ctx, d) {
  const secondary = d.secondary_color, accent = d.accent_color;
  if (d.back === 'cape') {
    const cape = [[248, 331], [352, 331], ...curve([352, 331], [391, 402], [399, 540], [435, 649]), [365, 627], [300, 658], [235, 627], [165, 649], ...curve([165, 649], [201, 540], [209, 402], [248, 331])];
    polygon(ctx, cape, secondary);
    polygon(ctx, [[259, 350], [245, 617], [187, 633], [221, 459]], light(secondary, .18), null);
    polygon(ctx, [[341, 350], [355, 617], [413, 633], [379, 459]], dark(secondary, .12), null);
    line(ctx, [[262, 379], [242, 603]], light(secondary, .45), 4);
    line(ctx, [[338, 379], [358, 603]], dark(secondary, .23), 4);
  } else if (d.back === 'wings') {
    const wing = [...curve([247, 356], [207, 288], [129, 225], [45, 248]), ...curve([45, 248], [44, 345], [83, 448], [180, 511]), ...curve([180, 511], [220, 493], [245, 440], [247, 356])];
    for (const points of [wing, mirror(wing)]) polygon(ctx, points, light(secondary, .32));
    const layers = [ [[61, 267], [105, 295], [172, 403], [139, 403], [85, 337]], [[94, 276], [132, 292], [206, 411], [178, 437], [135, 356]], [[134, 292], [166, 316], [225, 397], [208, 455], [188, 398]] ];
    layers.forEach((coords, index) => { for (const points of [coords, mirror(coords)]) polygon(ctx, points, light(secondary, .55 - index * .09), light(secondary, .05), 3); });
    for (const x of [220, 380]) ellipse(ctx, [x - 17, 385, x + 17, 419], accent, INK, 4);
  }
}
function legPose(side, motion, phase) {
  const angle = motion === 'walk' ? side * .22 * Math.sin(phase * TAU) : 0;
  const lift = motion === 'walk' ? Math.max(0, side * Math.cos(phase * TAU)) * 10 : 0;
  return { angle, lift, hip: [300 + side * 45, 526] };
}
function legPoint(point, pose) {
  const dx=point[0]-pose.hip[0],dy=point[1]-pose.hip[1];
  return [pose.hip[0]+dx*Math.cos(pose.angle)-dy*Math.sin(pose.angle),pose.hip[1]+dx*Math.sin(pose.angle)+dy*Math.cos(pose.angle)-pose.lift];
}
function legs(ctx, d, motion, phase) {
  const p = d.primary_color, s = d.secondary_color, a = d.accent_color;
  for (const side of [-1, 1]) {
    const x = 300 + side * 45;
    const pose=legPose(side,motion,phase);
    if(motion==='walk'){ctx.save();ctx.translate(pose.hip[0],pose.hip[1]-pose.lift);ctx.rotate(pose.angle);ctx.translate(-pose.hip[0],-pose.hip[1]);}
    pill(ctx, [[x, 526], [x + side * 5, 679]], p, 55);
    if (d.body_type === 'robot') {
      round(ctx, [x - 31, 580, x + 31, 622], 14, light(s, .18));
      for (const y of [590, 601, 612]) line(ctx, [[x - 14, y], [x + 14, y]], dark(s, .1), 3);
    } else line(ctx, [[x - 10, 558], [x - 13, 625]], light(p, .34), 7);
    if (d.boots === 'round') {
      round(ctx, [x - 35, 660, x + 35, 721], 18, s); round(ctx, [x - 44, 691, x + 40, 739], 20, s);
      round(ctx, [x - 44, 724, x + 40, 741], 8, dark(s, .22), INK, 4);
      line(ctx, [[x - 19, 681], [x + 19, 681]], a, 8); line(ctx, [[x - 26, 704], [x + 9, 704]], light(s, .52), 5);
    } else {
      polygon(ctx, [[x - 31, 650], [x + 29, 650], [x + 35, 691], [x + 45, 705], [x + 45, 738], [x - 43, 738], [x - 43, 704], [x - 34, 688]], s);
      polygon(ctx, [[x - 21, 658], [x + 19, 658], [x + 25, 684], [x - 24, 684]], a, INK, 3);
      line(ctx, [[x - 31, 708], [x + 34, 708]], light(s, .45), 5); line(ctx, [[x - 38, 729], [x + 39, 729]], INK, 5);
    }
    if(motion==='walk')ctx.restore();
  }
}
function hand(ctx, d, side, wrist, angle) {
  const p = d.primary_color, s = d.secondary_color, a = d.accent_color;
  const color = d.body_type === 'kid' ? d.skin_color : p;
  ctx.save(); ctx.translate(...wrist); ctx.rotate(angle);
  if (d.gloves === 'gauntlets') {
    round(ctx, [-30, -18, 30, 43], 19, s); round(ctx, [-33, -21, 33, -3], 7, a, INK, 4);
    line(ctx, [[-12, 11], [12, 11]], light(s, .5), 5);
    ellipse(ctx, [-side * 32 - 10, 0, -side * 32 + 10, 24], s, INK, 4);
  } else {
    round(ctx, [-24, -5, 24, 43], 18, color);
    ellipse(ctx, [-side * 24 - 9, 5, -side * 24 + 9, 26], color, INK, 4);
    line(ctx, [[side * 5, 27], [side * 14, 27]], dark(color, .22), 3);
  }
  ctx.restore();
}
function armPose(side, motion, phase) {
  const swing = Math.sin(phase * TAU);
  const shoulder = [300 + side * 76, 373];
  let elbow = [300 + side * 119, 423], wrist = [300 + side * 130, 483];
  if (motion === 'celebrate') { elbow = [300 + side * 126, 318]; wrist = [300 + side * (155 + 6 * swing), 236 + 9 * swing]; }
  else if (motion === 'wave' && side === 1) { elbow = [462, 341]; wrist = [461 + 17 * swing, 250]; }
  else if (motion === 'talk') { elbow = [300 + side * 122, 425]; wrist = [300 + side * (140 + 5 * swing), 468 - 8 * swing]; }
  else if (motion === 'walk') { elbow = [300 + side * (119 + 22 * swing), 422]; wrist = [300 + side * (130 + 48 * swing), 478 - side * 12 * swing]; }
  else if (motion === 'point' && side === 1) { elbow = [440, 356]; wrist = [505, 347 + 3 * swing]; }
  else if (motion === 'carry') { elbow = side === 1 ? [429, 405] : [270, 423]; wrist = side === 1 ? [458, 437] : [347, 439]; }
  else if (motion === 'give') { elbow = side === 1 ? [437, 373] : [302, 399]; wrist = side === 1 ? [500, 389] : [405, 398]; }
  else if (motion === 'think' && side === 1) { elbow = [429, 385]; wrist = [365, 284]; }
  const angle = Math.atan2(wrist[1] - elbow[1], wrist[0] - elbow[0]) - Math.PI / 2;
  // The drawn palm occupies local y=14 relative to the wrist attachment.
  const palm = [wrist[0] - 14 * Math.sin(angle), wrist[1] + 14 * Math.cos(angle)];
  return { shoulder, elbow, wrist, angle, palm };
}
function arms(ctx, d, motion, phase) {
  for (const side of [-1, 1]) {
    const {shoulder,elbow,wrist,angle}=armPose(side,motion,phase);
    pill(ctx, [shoulder, elbow, wrist], d.primary_color, 47);
    if (d.body_type === 'robot') {
      ellipse(ctx, [elbow[0] - 21, elbow[1] - 21, elbow[0] + 21, elbow[1] + 21], d.secondary_color);
      ellipse(ctx, [elbow[0] - 9, elbow[1] - 9, elbow[0] + 9, elbow[1] + 9], d.accent_color, INK, 3);
    } else line(ctx, [[elbow[0] - side * 5, elbow[1] + 4], [elbow[0] + (wrist[0] - elbow[0]) * .65 - side * 5, elbow[1] + (wrist[1] - elbow[1]) * .65]], light(d.primary_color, .32), 7);
    hand(ctx, d, side, wrist, angle);
  }
}
function torso(ctx, d) {
  const p = d.primary_color, s = d.secondary_color, a = d.accent_color;
  round(ctx, [270, 312, 330, 370], 18, d.body_type === 'kid' ? d.skin_color : p);
  if (d.body_type === 'robot') {
    round(ctx, [210, 344, 390, 553], 36, p); round(ctx, [230, 369, 370, 517], 24, light(p, .42), INK, 4);
    for (const x of [229, 371]) { ellipse(ctx, [x - 6, 356, x + 6, 368], a, INK, 3); ellipse(ctx, [x - 6, 529, x + 6, 541], a, INK, 3); }
    round(ctx, [272, 509, 328, 526], 6, s, INK, 3);
    for (const x of [285, 300, 315]) line(ctx, [[x, 514], [x, 520]], light(s, .7), 3);
  } else if (d.body_type === 'creature') {
    ellipse(ctx, [204, 337, 396, 568], p); ellipse(ctx, [230, 366, 370, 543], light(p, .62), null);
    arc(ctx, [233, 498, 367, 552], 15, 165, light(p, .3), 5);
  } else {
    round(ctx, [217, 342, 383, 555], 51, p);
    polygon(ctx, [[225, 391], [249, 403], [256, 506], [229, 515]], dark(p, .12), null);
    polygon(ctx, [[375, 391], [351, 403], [344, 506], [371, 515]], dark(p, .12), null);
    arc(ctx, [239, 346, 361, 427], 25, 155, light(p, .36), 5);
  }
  for (const side of [-1, 1]) {
    const x = 300 + side * 78; ellipse(ctx, [x - 29, 351, x + 29, 401], s);
    arc(ctx, [x - 20, 358, x + 20, 390], 190, 305, light(s, .5), 4);
  }
  round(ctx, [256, 341, 344, 361], 9, s, INK, 4); round(ctx, [222, 512, 378, 539], 10, s);
  round(ctx, [281, 509, 319, 542], 7, a, INK, 4); line(ctx, [[290, 519], [310, 519]], light(a, .45), 3);
}
function badge(ctx, d) {
  const a = d.accent_color;
  if (d.chest === 'star') {
    const points = Array.from({ length: 10 }, (_, i) => { const angle = -Math.PI / 2 + i * Math.PI / 5, r = i % 2 ? 16 : 35; return [300 + Math.cos(angle) * r, 434 + Math.sin(angle) * r]; });
    polygon(ctx, points, a, INK, 4); line(ctx, [[300, 410], [296, 428], [281, 435]], light(a, .65), 4);
  } else if (d.chest === 'bolt') {
    polygon(ctx, [[302, 396], [276, 439], [297, 439], [289, 472], [327, 424], [305, 424], [319, 396]], a, INK, 4);
    line(ctx, [[308, 405], [292, 430]], light(a, .6), 4);
  } else if (d.chest === 'gem') {
    polygon(ctx, [[284, 402], [316, 402], [335, 425], [300, 469], [265, 425]], a, INK, 4);
    line(ctx, [[284, 404], [279, 425], [300, 463], [321, 425], [316, 404]], dark(a, .18), 3);
    line(ctx, [[270, 425], [330, 425]], dark(a, .18), 3);
    polygon(ctx, [[287, 408], [309, 408], [300, 425], [279, 425]], light(a, .58), null);
  } else if (d.chest === 'reactor') {
    ellipse(ctx, [263, 397, 337, 471], d.secondary_color, INK, 4); ellipse(ctx, [272, 406, 328, 462], a, INK, 4);
    ellipse(ctx, [282, 416, 318, 452], light(a, .73), null); line(ctx, [[284, 425], [300, 443], [316, 425]], dark(a, .15), 4);
  }
}
function headShape(ctx, d, color, inset = 0, outline = INK, width = 6) {
  if (d.head_shape === 'round') round(ctx, [176 + inset, 123 + inset, 424 - inset, 338 - inset], 85 - inset * .3, color, outline, width);
  else polygon(ctx, [[227 + inset * .3, 123 + inset], [373 - inset * .3, 123 + inset], [424 - inset, 174 + inset * .3], [418 - inset, 276 - inset * .3], [370 - inset * .3, 338 - inset], [230 + inset * .3, 338 - inset], [182 + inset, 276 - inset * .3], [176 + inset, 174 + inset * .3]], color, outline, width);
}
function headBack(ctx, d) {
  const p = d.primary_color, a = d.accent_color;
  if (d.headwear === 'ears') {
    const outer = [[182, 181], [174, 65], [244, 135]], inner = [[191, 149], [188, 92], [221, 135]];
    for (const [outside, inside] of [[outer, inner], [mirror(outer), mirror(inner)]]) { polygon(ctx, outside, p); polygon(ctx, inside, light(a, .26), null); }
  } else if (d.headwear === 'antenna') {
    for (const side of [-1, 1]) {
      const tipX = 300 + side * 71; pill(ctx, [[300 + side * 49, 143], [tipX, 78]], d.secondary_color, 12);
      ellipse(ctx, [tipX - 16, 51, tipX + 16, 83], a, INK, 4); ellipse(ctx, [tipX - 8, 57, tipX, 65], light(a, .68), null);
    }
  }
  const color = d.body_type === 'kid' ? d.skin_color : p;
  for (const x of [178, 422]) {
    if (d.body_type === 'robot') { round(ctx, [x - 21, 196, x + 21, 254], 13, d.secondary_color); line(ctx, [[x - 5, 208], [x - 5, 241]], light(d.secondary_color, .45), 4); }
    else { ellipse(ctx, [x - 18, 209, x + 18, 259], color); arc(ctx, [x - 9, 222, x + 9, 246], 110, 260, dark(color, .16), 3); }
  }
}
function eyes(ctx, d, blink) {
  if (d.eyes === 'visor') {
    round(ctx, [209, 201, 391, 254], 25, INK, INK, 4); round(ctx, [218, 208, 382, 245], 18, '#78DDE2', null);
    if (blink) line(ctx, [[240, 226], [360, 226]], '#D9FFFF', 4);
    else { line(ctx, [[238, 215], [269, 215]], '#D9FFFF', 7); line(ctx, [[278, 215], [291, 215]], '#D9FFFF', 7); line(ctx, [[346, 217], [364, 237]], '#A9F1EF', 7); }
    return;
  }
  for (const x of [252, 348]) {
    if (blink) arc(ctx, [x - 20, 220, x + 20, 240], 8, 172, INK, 6);
    else if (d.eyes === 'round') {
      ellipse(ctx, [x - 21, 202, x + 21, 254], '#FFFFFF', INK, 4); ellipse(ctx, [x - 10, 215, x + 10, 246], INK, null);
      ellipse(ctx, [x - 5, 219, x + 2, 227], '#FFFFFF', null);
    } else { arc(ctx, [x - 21, 214, x + 21, 250], 190, 350, INK, 7); line(ctx, [[x - 16, 215], [x - 12, 211]], INK, 4); }
  }
}
function head(ctx, d, motion, phase) {
  const p = d.primary_color, s = d.secondary_color, a = d.accent_color, skin = d.skin_color;
  const face = d.body_type === 'kid' ? skin : p;
  const mask = d.headwear === 'web_mask', helmet = d.headwear === 'helmet';
  headShape(ctx, d, face);
  if (mask) {
    headShape(ctx, d, p); const web = light(p, .52);
    for (const points of [ [[300, 129], [300, 206]], [[219, 145], [268, 202]], [[381, 145], [332, 202]], [[181, 207], [235, 222]], [[419, 207], [365, 222]], [[194, 288], [237, 263]], [[406, 288], [363, 263]], [[259, 331], [275, 283]], [[341, 331], [325, 283]] ]) line(ctx, points, web, 3);
    arc(ctx, [221, 139, 379, 228], 185, 355, web, 3); arc(ctx, [193, 160, 407, 272], 185, 355, web, 3); arc(ctx, [212, 231, 388, 319], 5, 175, web, 3);
  } else if (d.body_type === 'robot') {
    headShape(ctx, d, light(p, .75), 18, INK, 4); for (const x of [207, 393]) ellipse(ctx, [x - 6, 155, x + 6, 167], a, INK, 2);
  } else if (d.body_type === 'creature') ellipse(ctx, [226, 248, 374, 328], light(p, .64), null);
  else polygon(ctx, [[186, 192], [194, 153], [230, 129], [369, 129], [401, 150], [414, 188], [382, 169], [362, 186], [331, 161], [300, 180], [271, 161], [242, 183], [217, 173]], dark(s, .25), INK, 4);
  if (helmet) {
    headShape(ctx, d, s); round(ctx, [195, 166, 405, 316], 58, face, INK, 5);
    if (d.body_type === 'robot') round(ctx, [206, 178, 394, 305], 50, light(p, .76), null);
    polygon(ctx, [[242, 132], [358, 132], [346, 163], [254, 163]], a, INK, 4); line(ctx, [[216, 151], [231, 143]], light(s, .54), 6);
    for (const x of [183, 417]) { ellipse(ctx, [x - 16, 228, x + 16, 272], a, INK, 4); line(ctx, [[x, 240], [x, 257]], dark(a, .15), 4); }
  }
  eyes(ctx, d, phase > .87);
  if (d.body_type === 'creature' && !mask && !helmet) { round(ctx, [288, 261, 312, 278], 8, INK, null); line(ctx, [[300, 276], [300, 288]], INK, 3); }
  else if (d.body_type === 'kid' && !mask) arc(ctx, [291, 249, 309, 265], 0, 165, dark(skin, .2), 3);
  if (motion === 'talk' && Math.sin(phase * TAU * 2) > -.25) {
    const opening = 13 + 4 * Math.sin(phase * TAU * 2);
    ellipse(ctx, [281, 279, 319, 286 + opening], INK, null); ellipse(ctx, [287, 282 + opening, 313, 286 + opening], '#EA97A5', null);
  } else arc(ctx, [277, 269, 323, 303], 8, 172, INK, 5);
  if (!mask && d.eyes !== 'visor') {
    const blush = d.body_type === 'kid' ? '#E99B96' : light(a, .25); for (const x of [231, 369]) ellipse(ctx, [x - 13, 263, x + 13, 276], blush, null);
  }
}

function newCanvas(width, height) {
  if (typeof document === 'undefined') throw new Error('Character previews need a browser canvas.');
  const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height; return canvas;
}
function drawingKey(character) { return character.image; }
function requireDrawingURL(source) {
  if (typeof source !== 'string' || source.length > MAX_IMAGE_LENGTH || !/^data:image\/(?:png|jpeg);base64,[a-z0-9+/]+=*$/i.test(source) || (source.length - source.indexOf(',') - 1) * .75 > 8 * 1024 * 1024 + 2) {
    throw new Error('Choose a PNG or JPEG drawing smaller than 8 MB.');
  }
}
function decodeImage(source) {
  requireDrawingURL(source);
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      if (!image.naturalWidth || !image.naturalHeight || image.naturalWidth * image.naturalHeight > MAX_PIXELS) reject(new Error('Choose a drawing with fewer than 12 million pixels.'));
      else resolve(image);
    };
    image.onerror = () => reject(new Error('This drawing could not be opened. Try another PNG or JPEG.'));
    image.src = source;
  });
}

/** Bounds of the visible ink, without changing the source image or its pixels.
 * Right and bottom are exclusive canvas edges, so even a one-pixel mark has
 * positive width/height. Alpha below 9 is only antialiasing noise.
 */
export function drawingInkBounds(image){
  if(!image||!Number.isInteger(image.width)||!Number.isInteger(image.height)||image.width<=0||image.height<=0||image.width*image.height>MAX_PIXELS||!ArrayBuffer.isView(image.data)||image.data.BYTES_PER_ELEMENT!==1||image.data.length!==image.width*image.height*4)throw new Error('Choose a supported drawing pixel buffer.');
  const {width,height,data}=image;let left=width,top=height,right=-1,bottom=-1;
  for(let y=0;y<height;y++)for(let x=0;x<width;x++)if(data[(y*width+x)*4+3]>8){left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);}
  if(right<left)return null;
  right++;bottom++;
  return Object.freeze({left,top,right,bottom,width:right-left,height:bottom-top,centerX:(left+right)/2,centerY:(top+bottom)/2});
}

/* Only remove near-white paper connected to the border. Enclosed white details stay. */
function paperToAlpha(canvas) {
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const image = ctx.getImageData(0, 0, canvas.width, canvas.height), pixels = image.data;
  const width = canvas.width, height = canvas.height, count = width * height;
  const seen = new Uint8Array(count), queue = new Uint32Array(count);
  let tail = 0;
  const enqueue = index => {
    if (seen[index]) return; seen[index] = 1; const at = index * 4;
    if (pixels[at + 3] < 8 || Math.min(pixels[at], pixels[at + 1], pixels[at + 2]) > 246) queue[tail++] = index;
  };
  for (let x = 0; x < width; x += 1) { enqueue(x); enqueue((height - 1) * width + x); }
  for (let y = 0; y < height; y += 1) { enqueue(y * width); enqueue(y * width + width - 1); }
  for (let head = 0; head < tail; head += 1) {
    const index = queue[head], x = index % width, y = Math.floor(index / width); pixels[index * 4 + 3] = 0;
    if (x) enqueue(index - 1); if (x + 1 < width) enqueue(index + 1); if (y) enqueue(index - width); if (y + 1 < height) enqueue(index + width);
  }
  ctx.putImageData(image, 0, 0);
  return drawingInkBounds(image);
}

export async function prepareCharacter(character) {
  if (!character || !['builder', 'drawing'].includes(character.source)) throw new Error('Choose a saved character.');
  if (character.source === 'builder') { normalizeDesign(character.design); return; }
  const key = drawingKey(character); requireDrawingURL(key);
  if (drawingCache.has(key)) { const cached = drawingCache.get(key); drawingCache.delete(key); drawingCache.set(key, cached); return; }
  const image = await decodeImage(key), canvas = newCanvas(600, 800), ctx = canvas.getContext('2d');
  const fit = Math.min(560 / image.naturalWidth, 760 / image.naturalHeight);
  ctx.drawImage(image, (600 - image.naturalWidth * fit) / 2, (800 - image.naturalHeight * fit) / 2, image.naturalWidth * fit, image.naturalHeight * fit);
  const bounds=paperToAlpha(canvas);
  if (!bounds) throw new Error('Add some colored lines before saving your drawing as a character.');
  drawingCache.set(key, canvas);
  drawingBoundsCache.set(key,bounds);
  while (drawingCache.size > 24){const expired=drawingCache.keys().next().value;drawingCache.delete(expired);drawingBoundsCache.delete(expired);}
}

function frameGeometry(character, x, y, width, height, {motion='idle',time=0,facing='right',speaking=false,walking=false}={}) {
  if (![x,y,width,height,time].every(Number.isFinite)||x<0||y<0||width<=0||height<=0||time<0||x>1e7||y>1e7||width>8192||height>8192||time>1e12) throw new Error('Choose a finite, nonnegative character position and a supported positive size.');
  if (!MOTIONS.has(motion)) throw new Error('Choose a supported character movement.');
  if (!['left','right'].includes(facing)) throw new Error('Choose a left or right character direction.');
  if (typeof speaking!=='boolean') throw new Error('Choose whether the character is speaking.');
  if (typeof walking!=='boolean') throw new Error('Choose whether the character is walking.');
  if(!character||!['builder','drawing'].includes(character.source))throw new Error('Choose a saved character.');
  const design=character.source==='builder'?normalizeDesign(character.design):null;
  const phase=((time/1.6)%1+1)%1,swing=Math.sin(phase*TAU),fit=Math.min(width/600,height/800);
  const walkLike=walking||motion==='walk';
  const body={dy:walkLike?-5*Math.abs(swing):0,angle:0,scale:1};
  if(character.source==='drawing') {
    body.dy=(motion==='celebrate'?-7:walkLike?-9:3)*swing;
    body.angle=motion==='wave'?.035*swing:motion==='celebrate'?.025*swing:walkLike?.025*swing:motion==='point'||motion==='give'?-.035:motion==='think'?-.025:0;
    body.scale=motion==='celebrate'?1+.018*swing:1;
  }
  return {motion,time,facing,speaking,walking:walkLike,phase,fit,body,design,baseX:x+(width-600*fit)/2,baseY:y+(height-800*fit)/2};
}
function worldPoint(point, frame, isDrawing) {
  let [x,y]=point;
  if(isDrawing){const dx=(x-300)*frame.body.scale,dy=(y-400)*frame.body.scale;const c=Math.cos(frame.body.angle),s=Math.sin(frame.body.angle);x=300+dx*c-dy*s;y=400+frame.body.dy+dx*s+dy*c;}
  else y+=frame.body.dy;
  if(frame.facing==='left')x=600-x;
  return {x:frame.baseX+x*frame.fit,y:frame.baseY+y*frame.fit};
}

/** Attachment points use the exact same pose and fit as drawCharacter.
 * leftHand/rightHand name the original facing-right rig; facing mirrors their
 * output positions, so rightHand remains the forward hand in a point pose.
 * For drawings these are logical beside-body interaction points, not invented
 * joints. No drawing pixels or features are modified by an anchor request.
 */
export function characterAnchors(character,x,y,width,height,options={}) {
  const frame=frameGeometry(character,x,y,width,height,options),drawing=character.source==='drawing';
  let leftHand,rightHand,head=[300,230],feet,prop,body=[300,450];
  if(drawing){
    const bounds=drawingBoundsCache.get(drawingKey(character));
    if(bounds){
      const middle=bounds.top+bounds.height*.6;
      leftHand=[Math.max(12,bounds.left-18),middle];rightHand=[Math.min(588,bounds.right+18),middle];
      body=[bounds.centerX,middle];head=[bounds.centerX,bounds.top+bounds.height*.22];feet=[bounds.centerX,bounds.bottom];prop=rightHand;
    }else{leftHand=[145,450];rightHand=[455,450];feet=[300,780];prop=[455,425];body=[300,450];}
  }
  else {
    leftHand=armPose(-1,frame.motion,frame.phase).palm;rightHand=armPose(1,frame.motion,frame.phase).palm;
    const soles=[-1,1].map(side=>legPoint([300+side*45,741],legPose(side,frame.walking?'walk':frame.motion,frame.phase)));
    feet=[(soles[0][0]+soles[1][0])/2,Math.max(soles[0][1],soles[1][1])];
    prop=['carry','give'].includes(frame.motion)?[(leftHand[0]+rightHand[0])/2,Math.min(leftHand[1],rightHand[1])-24]:rightHand;
  }
  return Object.fromEntries(Object.entries({leftHand,rightHand,head,feet,prop,body}).map(([key,point])=>[key,worldPoint(point,frame,drawing)]));
}

export function drawCharacter(ctx, character, x, y, width, height, options = {}) {
  const frame=frameGeometry(character,x,y,width,height,options),{motion,phase,fit,facing,speaking}=frame;
  ctx.save();
  try {
    ctx.translate(frame.baseX,frame.baseY); ctx.scale(fit, fit);
    if(facing==='left'){ctx.translate(600,0);ctx.scale(-1,1);}
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    if (character?.source === 'drawing') {
      const image = drawingCache.get(drawingKey(character));
      if (!image) throw new Error('Prepare this drawing before previewing it.');
      ctx.translate(300,400+frame.body.dy);ctx.rotate(frame.body.angle);ctx.scale(frame.body.scale,frame.body.scale);ctx.drawImage(image,-300,-400,600,800);
      return;
    }
    const design=frame.design,frontArms=['carry','give','point','think'].includes(motion);
    if(frame.body.dy)ctx.translate(0,frame.body.dy);
    back(ctx,design);legs(ctx,design,frame.walking?'walk':motion,phase);
    if(!frontArms)arms(ctx,design,motion,phase);
    torso(ctx,design);badge(ctx,design);
    if(frontArms&&motion!=='think')arms(ctx,design,motion,phase);
    headBack(ctx,design);head(ctx,design,speaking?'talk':motion,phase);
    if(motion==='think')arms(ctx,design,motion,phase);
  } finally { ctx.restore(); }
}

export async function characterPreview(character, { width = 300, height = 400, motion = 'idle', time = 0, facing='right',speaking=false,walking=false } = {}) {
  if (![width, height].every(value => Number.isInteger(value) && value >= 64 && value <= 2048)) throw new Error('Choose a preview from 64 to 2048 pixels.');
  await prepareCharacter(character);
  const canvas = newCanvas(width, height); drawCharacter(canvas.getContext('2d'), character, 0, 0, width, height, { motion, time, facing, speaking, walking });
  return canvas.toDataURL('image/png');
}

export class DrawingPad {
  constructor(canvas, { onChange = () => {} } = {}) {
    if (!canvas?.getContext || !canvas.width || !canvas.height || canvas.width * canvas.height > MAX_PIXELS) throw new Error('Choose a supported drawing canvas.');
    this.canvas = canvas; this.ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (!this.ctx) throw new Error('This browser cannot open the drawing canvas. You can still build a character.');
    this.onChange = onChange; this.tool = 'pen'; this.color = '#363249'; this.size = 10; this.mirror = false;
    this._hasDrawing = false; this._gesture = null; this._history = []; this._index = -1; this._loading = false; this._disposed = false;
    this._handlers = { pointerdown: event => this._start(event), pointermove: event => this._move(event), pointerup: event => this._end(event), pointercancel: event => this._end(event), lostpointercapture: event => this._end({ ...event, pointerId: event.pointerId, type: 'pointercancel' }) };
    for (const [name, handler] of Object.entries(this._handlers)) canvas.addEventListener(name, handler);
    canvas.style.touchAction = 'none'; this._white(); this._push(false);
  }
  setTool(tool) { if (!TOOLS.has(tool)) throw new Error('Choose a drawing tool.'); if (!this._gesture) this.tool = tool; }
  setColor(color) { if (!HEX.test(color)) throw new Error('Choose a six-digit drawing color.'); this.color = color; }
  setSize(size) { if (!Number.isFinite(Number(size)) || Number(size) < 1 || Number(size) > 80) throw new Error('Choose a brush size from 1 to 80.'); this.size = Number(size); }
  setMirror(enabled) { if (!this._gesture) this.mirror = Boolean(enabled); }
  hasDrawing() { return this._hasDrawing; }
  canUndo() { return !this._gesture && !this._loading && this._index > 0; }
  canRedo() { return !this._gesture && !this._loading && this._index >= 0 && this._index < this._history.length - 1; }
  getPNG() { return this.canvas.toDataURL('image/png'); }
  _white() { this.ctx.save(); this.ctx.setTransform(1, 0, 0, 1, 0, 0); this.ctx.fillStyle = '#FFFFFF'; this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height); this.ctx.restore(); }
  _notify() { this.onChange({ hasDrawing: this.hasDrawing(), canUndo: this.canUndo(), canRedo: this.canRedo() }); }
  _snapshot() { return this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height); }
  _push(notify = true) {
    const image = this._snapshot(), previous = this._history[this._index];
    if (previous && previous.hasDrawing === this._hasDrawing && previous.image.data.every((value, index) => value === image.data[index])) { if (notify) this._notify(); return; }
    this._history.splice(this._index + 1); this._history.push({ image, hasDrawing: this._hasDrawing });
    if (this._history.length > 24) this._history.shift(); this._index = this._history.length - 1; if (notify) this._notify();
  }
  _moveHistory(offset) {
    if (this._gesture || this._loading) return false;
    const index = this._index + offset;
    if (index < 0 || index >= this._history.length) return false;
    const entry = this._history[index]; this.ctx.putImageData(entry.image, 0, 0); this._index = index; this._hasDrawing = entry.hasDrawing; this._notify(); return true;
  }
  undo() { return this._moveHistory(-1); }
  redo() { return this._moveHistory(1); }
  clear() { if (this._gesture || this._loading) return false; this._white(); this._hasDrawing = false; this._push(); return true; }
  async load(source) {
    if (this._gesture || this._loading || this._disposed) return false;
    this._loading = true;
    try {
      const image = await decodeImage(source); if (this._disposed) return false;
      this._white(); const scale = Math.min(this.canvas.width / image.naturalWidth, this.canvas.height / image.naturalHeight);
      this.ctx.drawImage(image, (this.canvas.width - image.naturalWidth * scale) / 2, (this.canvas.height - image.naturalHeight * scale) / 2, image.naturalWidth * scale, image.naturalHeight * scale);
      this._hasDrawing = true; this._loading = false; this._push(); return true;
    } finally { this._loading = false; this._notify(); }
  }
  _point(event) {
    const box = this.canvas.getBoundingClientRect();
    return { x: Math.max(0, Math.min(this.canvas.width - 1, (event.clientX - box.left) * this.canvas.width / Math.max(1, box.width))), y: Math.max(0, Math.min(this.canvas.height - 1, (event.clientY - box.top) * this.canvas.height / Math.max(1, box.height))) };
  }
  _mirrored(at) { return { x: this.canvas.width - 1 - at.x, y: at.y }; }
  _brush(from, to) {
    const ctx = this.ctx; ctx.save(); ctx.strokeStyle = this.tool === 'eraser' ? '#FFFFFF' : this.color; ctx.fillStyle = ctx.strokeStyle;
    ctx.lineWidth = this.size * (this.tool === 'eraser' ? 2.2 : 1); ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.beginPath();
    if (from.x === to.x && from.y === to.y) { ctx.arc(to.x, to.y, ctx.lineWidth / 2, 0, TAU); ctx.fill(); }
    else { ctx.moveTo(from.x, from.y); ctx.lineTo(to.x, to.y); ctx.stroke(); }
    ctx.restore();
  }
  _stroke(from, to) { this._brush(from, to); if (this.mirror) this._brush(this._mirrored(from), this._mirrored(to)); }
  _shape(from, to) {
    const ctx = this.ctx; ctx.save(); ctx.strokeStyle = this.color; ctx.lineWidth = this.size; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.beginPath();
    if (this.tool === 'line') { ctx.moveTo(from.x, from.y); ctx.lineTo(to.x, to.y); }
    else if (this.tool === 'rectangle') ctx.rect(Math.min(from.x, to.x), Math.min(from.y, to.y), Math.max(1, Math.abs(to.x - from.x)), Math.max(1, Math.abs(to.y - from.y)));
    else ctx.ellipse((from.x + to.x) / 2, (from.y + to.y) / 2, Math.max(.5, Math.abs(to.x - from.x) / 2), Math.max(.5, Math.abs(to.y - from.y) / 2), 0, 0, TAU);
    ctx.stroke(); ctx.restore();
  }
  _preview(at) { this.ctx.putImageData(this._gesture.before, 0, 0); this._shape(this._gesture.start, at); if (this.mirror) this._shape(this._mirrored(this._gesture.start), this._mirrored(at)); }
  _floodFill(at) {
    const image = this._snapshot(), pixels = image.data, width = image.width, height = image.height;
    const start = Math.floor(at.y) * width + Math.floor(at.x), source = Array.from(pixels.slice(start * 4, start * 4 + 4));
    const color = this.color.match(/[0-9a-f]{2}/gi).map(value => parseInt(value, 16)).concat(255), tolerance = 24;
    if (source.every((value, channel) => Math.abs(value - color[channel]) <= tolerance)) return false;
    const count = width * height, seen = new Uint8Array(count), queue = new Uint32Array(count); let tail = 1; queue[0] = start; seen[start] = 1;
    const enqueue = index => {
      if (seen[index]) return; seen[index] = 1;
      if (source.every((value, channel) => Math.abs(value - pixels[index * 4 + channel]) <= tolerance)) queue[tail++] = index;
    };
    for (let head = 0; head < tail; head += 1) {
      const index = queue[head], x = index % width, y = Math.floor(index / width); pixels.set(color, index * 4);
      if (x) enqueue(index - 1); if (x + 1 < width) enqueue(index + 1); if (y) enqueue(index - width); if (y + 1 < height) enqueue(index + width);
    }
    this.ctx.putImageData(image, 0, 0); return true;
  }
  _start(event) {
    if (this._disposed || this._loading || this._gesture || event.pointerType === 'mouse' && event.button !== 0) return;
    event.preventDefault(); this.canvas.setPointerCapture(event.pointerId);
    const start = this._point(event); this._gesture = { pointerId: event.pointerId, start, last: start, before: this._snapshot(), hadDrawing: this._hasDrawing, changed: true };
    if (this.tool === 'fill') { this._gesture.changed = this._floodFill(start); if (this.mirror) this._gesture.changed = this._floodFill(this._mirrored(start)) || this._gesture.changed; }
    else if (this.tool === 'pen' || this.tool === 'eraser') this._stroke(start, start);
    else this._preview(start);
  }
  _move(event) {
    if (!this._gesture || event.pointerId !== this._gesture.pointerId || this.tool === 'fill') return;
    event.preventDefault();
    if (['line', 'rectangle', 'circle'].includes(this.tool)) { this._preview(this._point(event)); return; }
    const items = event.getCoalescedEvents?.() || [event];
    for (const item of items.length ? items : [event]) { const at = this._point(item); this._stroke(this._gesture.last, at); this._gesture.last = at; }
  }
  _end(event) {
    const gesture = this._gesture;
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    if (event.type === 'pointerup' && ['line', 'rectangle', 'circle'].includes(this.tool)) this._preview(this._point(event));
    this._gesture = null;
    if (this.canvas.hasPointerCapture(gesture.pointerId)) this.canvas.releasePointerCapture(gesture.pointerId);
    if (event.type === 'pointercancel' || event.type === 'lostpointercapture') { this.ctx.putImageData(gesture.before, 0, 0); this._hasDrawing = gesture.hadDrawing; this._notify(); }
    else if (gesture.changed) { this._hasDrawing = true; this._push(); }
  }
  dispose() {
    if (this._gesture) this._end({ pointerId: this._gesture.pointerId, type: 'pointercancel' });
    for (const [name, handler] of Object.entries(this._handlers)) this.canvas.removeEventListener(name, handler);
    this._disposed = true; this._history = []; this._index = -1;
  }
}
