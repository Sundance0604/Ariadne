import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from 'playwright-core';
import { chromeLaunchArgs } from './chromeBackend.mjs';
import { validateVisualPreset } from './src/visualPreset.js';
import { validateVisualStyle } from './src/visualStyle.js';
import { validateVisualSections } from './src/visualTimeline.js';

const [timelinePath, outputPath, timeArg] = process.argv.slice(2);
if (!timelinePath || !outputPath || !timeArg) {
  throw new Error('Usage: node render.mjs TIMELINE_JSON OUTPUT_PNG TIME_SECONDS');
}
const timeline = JSON.parse(readFileSync(resolve(timelinePath), 'utf8'));
const presetPath = process.env.WATERFALL_PRESET_FILE ?
  resolve(process.env.WATERFALL_PRESET_FILE) :
  new URL('./visual-preset.json', import.meta.url);
const preset = validateVisualPreset(JSON.parse(readFileSync(presetPath, 'utf8')));
const stylePath = process.env.WATERFALL_STYLE_FILE ?
  resolve(process.env.WATERFALL_STYLE_FILE) :
  new URL('./visual-style.json', import.meta.url);
const style = validateVisualStyle(JSON.parse(readFileSync(stylePath, 'utf8')));
validateVisualSections(timeline.visual_sections, validateVisualPreset);
const bundle = readFileSync(new URL('dist/waterfall.js', import.meta.url), 'utf8');
const width = Number(process.env.WATERFALL_WIDTH || 1920);
const height = Number(process.env.WATERFALL_HEIGHT || 1080);
let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.CHROME_BINARY || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: chromeLaunchArgs(),
  });
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  page.on('console', message => {
    if (message.type() === 'error' || message.type() === 'warning')
      process.stderr.write(`console ${message.type()}: ${message.text()}\n`);
  });
  page.on('pageerror', error => process.stderr.write(`page error: ${error.stack}\n`));
  await page.setContent('<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:#030205;overflow:hidden}canvas{display:block}</style>');
  await page.evaluate(value => { window.__WATERFALL_TIMELINE__ = value; }, timeline);
  await page.evaluate(value => { window.__WATERFALL_PRESET__ = value; }, preset);
  await page.evaluate(value => { window.__WATERFALL_STYLE__ = value; }, style);
  await page.evaluate(({ width, height }) => {
    window.__WATERFALL_WIDTH__ = width;
    window.__WATERFALL_HEIGHT__ = height;
  }, { width, height });
  await page.addScriptTag({ type: 'module', content: bundle });
  await page.waitForFunction(() => window.waterfallReady === true, { timeout: 60000 });
  const info = await page.evaluate(() => window.waterfallInfo);
  if (info.width !== width || info.height !== height) throw new Error('Renderer dimensions differ from export');
  let keyBrightness = 0;
  for (let pass = 0; pass < 20; pass++) {
    keyBrightness = await page.evaluate(async ({ time, materialTime }) => {
      if (window.__WATERFALL_TIMELINE__.intro) window.renderPresentationAt(time);
      else window.renderAt(time, materialTime);
      await new Promise(requestAnimationFrame);
      const canvas = document.querySelector('#waterfall-canvas');
      const probe = document.createElement('canvas'); probe.width = canvas.width; probe.height = canvas.height;
      const context = probe.getContext('2d', { willReadFrequently: true });
      context.drawImage(canvas, 0, 0);
      let total = 0, count = 0;
      for (let x = 40; x < canvas.width - 40; x += 40) {
        const pixel = context.getImageData(x, canvas.height - 30, 1, 1).data;
        total += (pixel[0] + pixel[1] + pixel[2]) / 3; count++;
      }
      return total / count;
    }, { time: Number(timeArg), materialTime: Number(process.env.WATERFALL_FLOW_TIME || timeArg) });
    if (keyBrightness > 60 ||
        (timeline.intro && Number(timeArg) < timeline.intro.keyboard_fade_end_seconds)) break;
    await page.waitForTimeout(100);
  }
  if (keyBrightness <= 60 &&
      !(timeline.intro && Number(timeArg) < timeline.intro.keyboard_fade_end_seconds) &&
      !(timeline.outro && Number(timeArg) >= timeline.outro.fade_start_seconds))
    throw new Error('The WebGL keyboard texture did not render');
  await page.screenshot({ path: resolve(outputPath), type: 'png' });
  process.stdout.write(JSON.stringify(info) + '\n');
} finally {
  if (browser) await browser.close();
}
