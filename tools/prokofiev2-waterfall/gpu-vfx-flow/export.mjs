import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import { createReadStream, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from 'playwright-core';
import { chromeLaunchArgs } from './chromeBackend.mjs';
import { validateVisualPreset } from './src/visualPreset.js';
import { validateVisualStyle } from './src/visualStyle.js';
import { validateVisualSections } from './src/visualTimeline.js';

const [timelinePath, audioPath, outputPath, fpsArg] = process.argv.slice(2);
if (!timelinePath || !audioPath || !outputPath) {
  throw new Error('Usage: node export.mjs TIMELINE_JSON AUDIO OUTPUT_MP4 [FPS]');
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
const audio = resolve(audioPath);
let fingerprint = process.env.WATERFALL_VERIFIED_AUDIO_SHA256;
if (!fingerprint) {
  const audioHash = createHash('sha256');
  for await (const block of createReadStream(audio)) audioHash.update(block);
  fingerprint = audioHash.digest('hex');
}
if (fingerprint !== timeline.sources.audio.sha256) throw new Error('Audio fingerprint differs from alignment source');
const bundle = readFileSync(new URL('dist/waterfall.js', import.meta.url), 'utf8');
const width = Number(process.env.WATERFALL_WIDTH || 1920);
const height = Number(process.env.WATERFALL_HEIGHT || 1080);
const fps = Number(fpsArg || 30);
// Each encoded frame is displayed for 1/fps seconds. Sample its midpoint so
// an attack cannot look up to one whole frame late during playback.
const visualLead = Number(process.env.WATERFALL_VISUAL_LEAD_SECONDS ?? (0.5 / fps));
const start = Number(process.env.WATERFALL_START || timeline.render_interval.start_seconds);
const duration = Number(process.env.WATERFALL_DURATION || timeline.render_interval.duration_seconds);
const introLead = Number(timeline.intro?.lead_in_seconds ?? 0);
if (!Number.isFinite(introLead) || introLead < 0 || introLead >= duration ||
    (introLead > 0 && start !== 0)) throw new Error('Invalid title lead-in');
const frames = Math.round(duration * fps);
if (!Number.isInteger(frames) || frames <= 0 || fps <= 0) throw new Error('Invalid duration or fps');
const encodePreset = process.env.WATERFALL_ENCODING_PRESET || 'fast';
const crf = Number(process.env.WATERFALL_CRF ?? 12);
const encodeThreads = Number(process.env.WATERFALL_ENCODER_THREADS ?? 4);
const videoOnly = process.env.WATERFALL_VIDEO_ONLY === '1';
if (!['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow'].includes(encodePreset) ||
    !Number.isInteger(crf) || crf < 0 || crf > 30 ||
    !Number.isInteger(encodeThreads) || encodeThreads < 1 || encodeThreads > 16)
  throw new Error('Invalid encoder settings');
const ffmpeg = spawn(process.env.FFMPEG_BINARY || 'ffmpeg', [
  '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
  '-f', 'image2pipe', '-framerate', String(fps), '-vcodec', 'png', '-i', 'pipe:0',
  ...(!videoOnly ? ['-ss', String(start), '-t', String(duration - introLead), '-i', audio] : []),
  '-map', '0:v:0', ...(!videoOnly ? ['-map', '1:a:0'] : []),
  '-c:v', 'libx264', '-threads', String(encodeThreads),
  '-preset', encodePreset,
  '-crf', String(crf), '-vf', 'scale=in_range=pc:out_range=tv,format=yuv420p',
  '-pix_fmt', 'yuv420p', '-color_range', 'tv',
  ...(!videoOnly ? [...(introLead > 0 ? ['-af',
    `adelay=${Math.round(introLead * 1000)}:all=1,apad=whole_dur=${duration}`] : []),
    '-c:a', 'aac', '-b:a', '192k'] : ['-an']),
  '-t', String(duration), '-movflags', '+faststart', resolve(outputPath),
], { stdio: ['pipe', 'ignore', 'pipe'] });
let ffmpegError = '';
ffmpeg.stderr.on('data', chunk => { ffmpegError += String(chunk).slice(-4000); });
let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.CHROME_BINARY || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: chromeLaunchArgs(),
  });
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  let pageError;
  page.on('pageerror', error => { pageError = error; });
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
  await page.evaluate(async time => {
    for (let pass = 0; pass < 3; pass++) {
      window.renderPresentationAt(time);
      await new Promise(requestAnimationFrame);
    }
  }, start);
  for (let index = 0; index < frames; index++) {
    if (pageError) throw pageError;
    const dataURL = await page.evaluate(time => window.exportFrame(time), start + index / fps + visualLead);
    const png = Buffer.from(dataURL.slice(dataURL.indexOf(',') + 1), 'base64');
    if (!ffmpeg.stdin.write(png)) await once(ffmpeg.stdin, 'drain');
    if ((index + 1) % Math.max(fps * 5, 1) === 0 || index + 1 === frames) {
      process.stdout.write(`frames ${index + 1}/${frames}\n`);
    }
  }
  ffmpeg.stdin.end();
  const [code] = await once(ffmpeg, 'close');
  if (code !== 0) throw new Error(`FFmpeg failed: ${ffmpegError.slice(-2000)}`);
  process.stdout.write(JSON.stringify({ frames, fps, width, height, start,
    duration, visualLead,
    presetSha256: createHash('sha256').update(JSON.stringify(preset)).digest('hex'),
    styleSha256: createHash('sha256').update(JSON.stringify(style)).digest('hex') }) + '\n');
} catch (error) {
  ffmpeg.kill('SIGKILL');
  throw error;
} finally {
  if (browser) await browser.close();
}
