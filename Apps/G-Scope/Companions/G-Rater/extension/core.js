// Shared by the extension and its Node tests. No page contents are read here.
export const BRIDGE = 'http://127.0.0.1:48135';
export const COPILOT = 'https://it.rutgers.edu/ai/microsoft-copilot/';

export function questionScope(address) {
  const url = new URL(address);
  if (url.protocol !== 'https:' || !['gradescope.com', 'www.gradescope.com'].includes(url.hostname)) {
    throw new Error('Open a Gradescope question grading page first.');
  }
  const match = url.pathname.match(/^\/courses\/(\d+)\/questions\/(\d+)\/submissions\/[^/]+\/grade\/?$/);
  if (!match) throw new Error('Open an individual submission in the question grading view.');
  // Used only to choose a local calibration; never put into an AI request.
  return `${match[1]}:${match[2]}`;
}

export function validateRect(rect, frame) {
  if (!rect || !['x', 'y', 'width', 'height'].every(k => Number.isFinite(rect[k]))) {
    throw new Error('Draw both capture regions first.');
  }
  if (rect.x < 0 || rect.y < 0 || rect.width < 40 || rect.height < 40 ||
      rect.x + rect.width > frame.width || rect.y + rect.height > frame.height) {
    throw new Error('Capture regions must fit inside the visible page and be at least 40 × 40 pixels.');
  }
}

export function checkLayout(profile, frame) {
  if (!profile?.frame) throw new Error('Set capture regions for this question first.');
  const a = profile.frame;
  for (const key of ['width', 'height', 'dpr', 'zoom', 'scrollX', 'scrollY']) {
    if (!Number.isFinite(frame[key]) || Math.abs(a[key] - frame[key]) > 0.01) {
      throw new Error('Window size, zoom, or scroll position changed. Set the regions again.');
    }
  }
  if (frame.dirty) throw new Error('The page moved. Set the regions again to confirm what is captured.');
  validateRect(profile.work, frame);
  validateRect(profile.rubric, frame);
}

export function sameView(before, after) {
  return before.href === after.href && before.epoch === after.epoch &&
    ['width', 'height', 'dpr', 'scrollX', 'scrollY'].every(k => before[k] === after[k]);
}

export function pixelRect(rect, frame, bitmap) {
  const sx = bitmap.width / frame.width;
  const sy = bitmap.height / frame.height;
  // Refuse unexpected viewport/screenshot geometry rather than shifting a crop.
  if (Math.abs(sx - sy) > 0.02 || Math.abs(sx - frame.dpr) > 0.05) {
    throw new Error('Display scaling changed. Recalibrate before capturing.');
  }
  // Round inward so no pixels outside the approved rectangle are included.
  const x = Math.ceil(rect.x * sx), y = Math.ceil(rect.y * sy);
  return { x, y, width: Math.floor((rect.x + rect.width) * sx) - x,
    height: Math.floor((rect.y + rect.height) * sy) - y };
}

export function makePayload(crops, guidance) {
  // This allowlist is the entire request body. No URL, name, IDs, HTML, or tab title.
  return { workImage: crops.work, rubricImage: crops.rubric, guidance: String(guidance || '').slice(0, 12000) };
}
