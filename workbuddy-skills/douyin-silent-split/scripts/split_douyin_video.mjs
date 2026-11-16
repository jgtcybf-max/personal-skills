#!/usr/bin/env node
/**
 * 抖音素材拆分：无音轨静音视频 + 独立 MP3，按「<M月D号>/<标题-id>/」归档。
 * stdout 只输出一段 JSON；进度与诊断走 stderr。
 */
import { spawnSync } from "node:child_process";
import {
  existsSync, mkdirSync, statSync, rmSync, copyFileSync, mkdtempSync,
} from "node:fs";
import { join, resolve, dirname, basename, extname } from "node:path";
import { tmpdir, homedir } from "node:os";
import { fileURLToPath } from "node:url";

const SKILL_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..");
// 素材库根目录：优先环境变量，否则取当前用户的桌面，便于分发给同事后直接可用。
const MATERIAL_ROOT =
  process.env.DOUYIN_MATERIAL_ROOT?.trim() || join(homedir(), "Desktop", "同行视频");
const AUDIO_DIR_NAME = "音频";
const MAX_STEM = 80;

/** 默认落到「同行视频\<M月D号>\」，与按日期归档的习惯一致（如 11月6号）。 */
function currentDayDir() {
  const now = new Date();
  return join(MATERIAL_ROOT, `${now.getMonth() + 1}月${now.getDate()}号`);
}
const DEFAULT_ROOT = currentDayDir();

let tmp = null;

function emit(obj) {
  process.stdout.write(JSON.stringify(obj, null, 2) + "\n");
}
function log(msg) {
  process.stderr.write(`[split] ${msg}\n`);
}
function cleanup() {
  if (tmp) {
    try { rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
    tmp = null;
  }
}
function fail(error, warnings = []) {
  cleanup();
  emit({ ok: false, error, warnings });
  process.exit(1);
}
function findFfmpeg() {
  const candidates = [
    process.env.DOUYIN_FFMPEG_PATH,
    process.env.FFMPEG_PATH,
    join(SKILL_DIR, "bin", "ffmpeg.exe"),
  ].filter(Boolean);
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  const probe = spawnSync(process.platform === "win32" ? "where.exe" : "which", ["ffmpeg"], { encoding: "utf8" });
  if (probe.status === 0) {
    const first = (probe.stdout || "").split(/\r?\n/).map((s) => s.trim()).find(Boolean);
    if (first && existsSync(first)) return first;
  }
  return null;
}
function findDownloadScript() {
  const candidates = [
    process.env.DOUYIN_DOWNLOAD_SCRIPT,
    resolve(SKILL_DIR, "..", "douyin-video-download", "scripts", "download_douyin_video.mjs"),
    join(homedir(), ".workbuddy", "skills", "douyin-video-download", "scripts", "download_douyin_video.mjs"),
  ].filter(Boolean);
  return candidates.find((c) => existsSync(c)) || null;
}
function parseJsonLoose(text) {
  const s = (text || "").trim();
  const start = s.indexOf("{");
  const end = s.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try { return JSON.parse(s.slice(start, end + 1)); } catch { return null; }
}
function mb(size) { return +(size / 1048576).toFixed(2); }

/** 清洗文件名并限制长度，避免 Windows 路径超限；超长时保留结尾的 -<awemeId>。 */
function safeStem(input, awemeId) {
  const cleaned = String(input ?? "")
    .replace(/[\\/:*?"<>|\u0000-\u001F]/g, "_")
    .replace(/\s+/g, " ")
    .trim();
  if (cleaned.length <= MAX_STEM) return cleaned || "douyin-video";
  const suffix = awemeId ? `-${awemeId}` : "";
  const keep = Math.max(MAX_STEM - suffix.length - 1, 20);
  const head = cleaned.slice(0, keep).trim();
  return `${head}${suffix}` || "douyin-video";
}

/** 同名文件已存在时不覆盖：自动追加 _2、_3…，视频与音频共用同一个 stem 保持配对。 */
function resolveStem(dir, base, needVideo, needAudio, force) {
  const exists = (s) =>
    (needVideo && existsSync(join(dir, `${s}.mp4`))) ||
    (needAudio && existsSync(join(dir, `${s}.mp3`)));
  if (force || !exists(base)) return { stem: base, renamed: false };
  let index = 2;
  while (exists(`${base}_${index}`)) index += 1;
  return { stem: `${base}_${index}`, renamed: true };
}

// ---------- 参数 ----------
const argv = process.argv.slice(2);
let outDir = DEFAULT_ROOT;
let layout = "per-item";
let quality = "highest";
let inputFile = null;
let audioOnly = false;
let trimSeconds = null;
let force = false;
const positional = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === "--help" || a === "-h") {
    emit({
      ok: true,
      help: "用法: node split_douyin_video.mjs [选项] \"<抖音分享文本或链接>\"  |  [选项] --input <本地mp4>",
      options: {
        "--out-dir <目录>": `素材库根目录，默认 ${DEFAULT_ROOT}（取运行当天）`,
        "--layout per-item|flat": "per-item：每条一个子文件夹（默认）；flat：旧平铺方式",
        "--quality highest|auto": "highest：取页面可用最高档（默认）；auto：原有默认清晰度",
        "--audio-only": "只导出 MP3，不生成静音视频",
        "--trim <秒>": "只保留前 N 秒（视频与音频同时截取）",
        "--force": "允许覆盖同名文件（默认自动改名 _2、_3…）",
        "--input <本地mp4>": "只处理本地文件，不访问抖音",
      },
    });
    process.exit(0);
  } else if (a === "--out-dir") {
    outDir = argv[++i];
    if (!outDir) fail("--out-dir 后面需要跟一个目录路径");
  } else if (a === "--layout") {
    layout = argv[++i];
  } else if (a === "--quality") {
    quality = argv[++i];
  } else if (a === "--input") {
    inputFile = argv[++i];
  } else if (a === "--audio-only") {
    audioOnly = true;
  } else if (a === "--force") {
    force = true;
  } else if (a === "--trim") {
    const raw = argv[++i];
    const value = Number(raw);
    if (!Number.isFinite(value) || value <= 0) fail(`--trim 需要跟一个正数秒值，收到：${raw}`);
    trimSeconds = value;
  } else {
    positional.push(a);
  }
}
if (!["flat", "per-item"].includes(layout)) fail(`未知的 --layout: ${layout}（可用 flat | per-item）`);
if (!["highest", "auto"].includes(quality)) fail(`未知的 --quality: ${quality}（可用 highest | auto）`);
const shareText = positional.join(" ").trim();
if (!inputFile && !shareText) fail("请提供抖音分享文本/链接，或用 --input 指定本地 MP4。");

const ffmpeg = findFfmpeg();
if (!ffmpeg) fail("未找到 ffmpeg。请把便携版放到本 skill 的 bin/ffmpeg.exe，或用 DOUYIN_FFMPEG_PATH 指定路径。");

const warnings = [];
let srcPath = null;
let meta = {};

try {
  tmp = mkdtempSync(join(tmpdir(), "dy-split-")).replace(/\\/g, "/");

  if (inputFile) {
    srcPath = resolve(inputFile);
    if (!existsSync(srcPath)) fail(`--input 指定的文件不存在：${srcPath}`, warnings);
    meta = { title: basename(srcPath, extname(srcPath)), author: "", awemeId: "", description: "", durationText: "" };
    log(`使用本地文件：${srcPath}`);
  } else {
    const dl = findDownloadScript();
    if (!dl) fail("未找到 douyin-video-download 的 download_douyin_video.mjs，请先安装该 skill。", warnings);
    log(`下载原始带音轨视频到临时目录（画质策略：${quality}）…`);
    const dlArgs = [dl, "--out-dir", tmp];
    if (quality === "highest") dlArgs.push("--prefer-highest-quality");
    dlArgs.push(shareText);
    const r = spawnSync(process.execPath, dlArgs, {
      encoding: "utf8", maxBuffer: 32 * 1024 * 1024, timeout: 180000,
      env: { ...process.env, DOUYIN_FFMPEG_PATH: ffmpeg },
    });
    if (r.stderr) process.stderr.write(r.stderr);
    const j = parseJsonLoose(r.stdout);
    if (!j || !j.ok || !j.savedPath || !existsSync(j.savedPath)) {
      fail(`下载失败：${j?.error || "下载脚本未返回有效结果"}`, warnings);
    }
    srcPath = j.savedPath;
    meta = j;
    if (Array.isArray(j.warnings)) warnings.push(...j.warnings.map((w) => `下载阶段：${w}`));
    log(`下载完成：${j.title || ""} / ${j.author || ""} / ${j.durationText || ""}`);
  }

  // 把源复制进临时区，避免 --input 指向目标路径时被覆盖
  const workSrc = join(tmp, "source" + (extname(srcPath) || ".mp4"));
  copyFileSync(srcPath, workSrc);

  const base = safeStem(basename(srcPath, extname(srcPath)), meta.awemeId);
  const root = resolve(outDir);
  const itemDir = layout === "per-item" ? join(root, base) : root;
  const audioDir = layout === "per-item" ? itemDir : join(root, AUDIO_DIR_NAME);

  mkdirSync(itemDir, { recursive: true });
  if (layout === "flat") mkdirSync(audioDir, { recursive: true });

  // 探测音轨，避免无音轨源生成空 MP3
  const probe = spawnSync(ffmpeg, ["-hide_banner", "-i", workSrc], { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
  const hasAudio = /Stream\s+#\d+:\d+.*Audio:/i.test(probe.stderr || "");
  if (audioOnly && !hasAudio) fail("源视频没有音轨，无法只导出音频。", warnings);

  const { stem, renamed } = resolveStem(itemDir, base, !audioOnly, hasAudio, force);
  let audioFileStem = stem;
  if (layout !== "per-item") {
    // flat 模式下音频落在 音频\ 子目录，需单独避让同名文件
    audioFileStem = resolveStem(audioDir, stem, false, hasAudio, force).stem;
    if (audioFileStem !== stem) {
      warnings.push(`音频目录已存在同名文件，音频保存为 ${audioFileStem}.mp3（与视频不再同名）。`);
    }
  }

  const videoPath = audioOnly ? null : join(itemDir, `${stem}.mp4`);
  const audioPath = join(audioDir, `${audioFileStem}.mp3`);
  const trimArgs = trimSeconds ? ["-t", String(trimSeconds)] : [];

  if (!audioOnly) {
    log(`拆出无音轨静音视频（-c:v copy -an${trimSeconds ? `，前 ${trimSeconds} 秒` : ""}）…`);
    const rv = spawnSync(ffmpeg, [
      "-y", "-hide_banner", "-loglevel", "error", "-i", workSrc,
      "-map", "0:v:0", "-c:v", "copy", "-an", ...trimArgs, "-movflags", "+faststart", videoPath,
    ], { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
    if (rv.status !== 0 || !existsSync(videoPath) || statSync(videoPath).size === 0) {
      fail(`生成静音视频失败：${(rv.stderr || "").trim().slice(0, 500)}`, warnings);
    }
  }

  let audioOk = false;
  if (hasAudio) {
    log(`导出独立 MP3（libmp3lame -q:a 2${trimSeconds ? `，前 ${trimSeconds} 秒` : ""}）…`);
    const ra = spawnSync(ffmpeg, [
      "-y", "-hide_banner", "-loglevel", "error", "-i", workSrc,
      "-vn", "-map", "0:a:0", "-c:a", "libmp3lame", "-q:a", "2", ...trimArgs, audioPath,
    ], { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
    if (ra.status === 0 && existsSync(audioPath) && statSync(audioPath).size > 0) {
      audioOk = true;
    } else {
      warnings.push(`MP3 导出失败：${(ra.stderr || "").trim().slice(0, 300)}`);
    }
  } else {
    warnings.push("源视频没有音轨，未生成 MP3；静音视频已正常产出。");
  }
  if (!audioOk && existsSync(audioPath)) {
    try { rmSync(audioPath, { force: true }); } catch { /* ignore */ }
  }

  // 归档自检：确认落在日期目录下的素材子文件夹里，且 mp4/mp3 同名同层
  const paired = audioOnly
    ? null
    : Boolean(videoPath && audioOk) &&
      dirname(videoPath) === dirname(audioPath) &&
      basename(videoPath, ".mp4") === basename(audioPath, ".mp3");
  const archive = {
    dayDir: basename(root),
    itemDir: layout === "per-item" ? basename(itemDir) : null,
    layout,
    paired,
    renamed,
  };
  if (layout === "per-item" && !audioOnly && !paired) {
    warnings.push("归档结构异常：静音视频与 MP3 未同名同层，请检查目录。");
  }
  if (renamed) warnings.push(`目标已存在同名文件，本次改名为 ${stem}（未覆盖原文件）。`);

  emit({
    ok: true,
    title: meta.title || "",
    author: meta.author || "",
    awemeId: meta.awemeId || "",
    description: meta.description || "",
    durationText: meta.durationText || "",
    strategy: inputFile ? "local-split" : "download-then-split",
    quality: meta.quality ?? null,
    qualityMode: inputFile ? null : quality,
    layout,
    audioOnly,
    trimSeconds,
    archive,
    videoPath,
    audioPath: audioOk ? audioPath : null,
    videoSizeMB: videoPath ? mb(statSync(videoPath).size) : null,
    audioSizeMB: audioOk ? mb(statSync(audioPath).size) : null,
    warnings,
  });
} catch (e) {
  fail(`执行异常：${e.message}`, warnings);
} finally {
  cleanup();
}
