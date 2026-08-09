#!/usr/bin/env node
/**
 * scripts/gen.mjs — Capsule Convention Angular generator (project-agnostic)
 *
 * Works in ANY Angular project — single-app or monorepo (e.g. apps/web/) —
 * by walking up from cwd to find angular.json, then reading an OPTIONAL
 * per-project `.tools` file at that root for overrides. No `.tools` file?
 * Sensible Angular-CLI-shaped defaults kick in automatically.
 *
 * ── Two calling conventions, auto-detected ─────────────────────────────────
 *
 * 1. Capsule Convention (CC) mode — <type> <name>
 *      node scripts/gen.mjs feature dark-mode-toggle
 *      node scripts/gen.mjs page    about
 *      node scripts/gen.mjs ui      avatar --scss
 *
 *    <type> must match one of the project's configured GEN_TYPES
 *    (default: feature, page, layout, ui). Lands in:
 *      <componentBase>/<type>/<name>/index.ts
 *
 * 2. Legacy / free-path mode — <path>, used whenever the first arg
 *    ISN'T a recognized type, or GEN_TYPES is disabled for the project:
 *      node scripts/gen.mjs pages/home
 *      node scripts/gen.mjs ui/dialog/password --name PasswordDialog
 *
 * ── Non-component generators (same in both projects/modes) ────────────────
 *      node scripts/gen.mjs --service editor-auth
 *      node scripts/gen.mjs --guard   lawyer-auth --name LawyerAuth
 *      node scripts/gen.mjs --pipe    safe-html -n SafeHtml
 *
 * ── Flags ───────────────────────────────────────────────────────────────────
 *   --name / -n <ClassName>   override the class/export name
 *   --scss                    also scaffold an index.<styleExt> file
 *   --service                 generate an injectable service
 *   --guard                   generate a functional route guard
 *   --pipe                    generate a standalone pipe
 *   --dry                     preview without writing
 *   --force                   overwrite existing files
 *
 * ── Per-project config (`.tools`, git-tracked, at the project root) ────────
 *   A plain KEY=VALUE file (same file dev_tools.zsh already reads for
 *   DEVTOOLS_NAV_ENTRY_POINTS). All keys optional:
 *
 *     GEN_COMPONENT_BASE=src/app/components
 *     GEN_SERVICE_BASE=src/app/core/services
 *     GEN_GUARD_BASE=src/app/core/guards
 *     GEN_PIPE_BASE=src/app/core/pipes
 *     GEN_TYPES=feature,page,layout,ui   # empty string "" disables CC mode
 *     GEN_PREFIX=app                     # selector prefix, e.g. "app-avatar"
 *     GEN_STYLE_EXT=scss                 # or css / sass
 *
 *   This is what makes the generator "dynamic": drop a differently-shaped
 *   `.tools` file into a different Angular project and the same script
 *   adapts — different base dirs, different selector prefix, different (or
 *   no) CC type restriction — with zero code changes.
 */

import fs   from 'fs';
import path from 'path';

// ── Colours ───────────────────────────────────────────────────────────────────
const c = {
  reset: '\x1b[0m', bold: '\x1b[1m', dim: '\x1b[2m',
  green: '\x1b[32m', yellow: '\x1b[33m', red: '\x1b[31m',
  cyan: '\x1b[36m', gray: '\x1b[90m', blue: '\x1b[34m',
};

const ok     = (s) => console.log(`  ${c.green}✓${c.reset}  ${s}`);
const skip   = (s) => console.log(`  ${c.yellow}–${c.reset}  ${c.dim}${s} (already exists)${c.reset}`);
const dryLog = (s) => console.log(`  ${c.cyan}~${c.reset}  ${c.dim}[dry]${c.reset} ${s}`);
const fatal  = (s) => { console.error(`\n  ${c.red}✗${c.reset}  ${s}\n`); process.exit(1); };
const info   = (s) => console.log(`  ${c.blue}i${c.reset}  ${c.dim}${s}${c.reset}`);

// ── Arg parsing ───────────────────────────────────────────────────────────────
const rawArgs = process.argv.slice(2);

function extractValueFlag(args, ...keys) {
  for (let i = 0; i < args.length; i++) {
    for (const key of keys) {
      if (args[i].startsWith(`${key}=`)) {
        return { value: args[i].slice(key.length + 1), filtered: [...args.slice(0, i), ...args.slice(i + 1)] };
      }
      if (args[i] === key && i + 1 < args.length && !args[i + 1].startsWith('-')) {
        return { value: args[i + 1], filtered: [...args.slice(0, i), ...args.slice(i + 2)] };
      }
    }
  }
  return { value: null, filtered: args };
}

const { value: customName, filtered: argsAfterName } = extractValueFlag(rawArgs, '--name', '-n');

const flags   = new Set(argsAfterName.filter(a => a.startsWith('-')));
const posArgs = argsAfterName.filter(a => !a.startsWith('-'));

const withScss  = flags.has('--scss');
const isDry     = flags.has('--dry');
const isForce   = flags.has('--force');
const isService = flags.has('--service');
const isGuard   = flags.has('--guard');
const isPipe    = flags.has('--pipe');

function printHelp() {
  console.log(`
  ${c.bold}gen.mjs${c.reset} — Capsule Convention Angular generator (project-agnostic)

  ${c.bold}CAPSULE CONVENTION MODE${c.reset}
    node scripts/gen.mjs <type> <name>              e.g. feature dark-mode-toggle
    node scripts/gen.mjs <type> <name> --name Foo    custom class name

  ${c.bold}LEGACY / FREE-PATH MODE${c.reset}  (used when <type> isn't recognized)
    node scripts/gen.mjs <path>
    node scripts/gen.mjs ui/dialog/password --name PasswordDialog

  ${c.bold}OTHER GENERATORS${c.reset}
    node scripts/gen.mjs --service <path>
    node scripts/gen.mjs --guard   <path>
    node scripts/gen.mjs --pipe    <path>

  ${c.bold}FLAGS${c.reset}
    --name / -n   override class/export name
    --scss        also create index.<styleExt>
    --dry         preview without writing
    --force       overwrite existing files

  ${c.bold}PER-PROJECT CONFIG${c.reset}  (optional .tools file at project root)
    GEN_COMPONENT_BASE, GEN_SERVICE_BASE, GEN_GUARD_BASE, GEN_PIPE_BASE,
    GEN_TYPES, GEN_PREFIX, GEN_STYLE_EXT
  `);
}

if (posArgs.length === 0 && !isService && !isGuard && !isPipe) {
  printHelp();
  process.exit(0);
}

// ── Project root detection (works for standalone AND monorepo apps/*) ────────

function findProjectRoot(start) {
  let dir = start;
  for (let i = 0; i < 10; i++) {
    if (fs.existsSync(path.join(dir, 'angular.json'))) return dir;
    const pkg = path.join(dir, 'package.json');
    if (fs.existsSync(pkg)) {
      try {
        const p = JSON.parse(fs.readFileSync(pkg, 'utf8'));
        if (p.dependencies?.['@angular/core'] || p.devDependencies?.['@angular/core']) return dir;
      } catch {}
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

const root = findProjectRoot(process.cwd());
if (!root) fatal('Could not find an Angular project root (no angular.json / @angular/core found). Run from inside an Angular project.');

// ── Per-project config (.tools) — grep-free, awk-friendly KEY=VALUE parsing ──

const DEFAULT_CONFIG = {
  GEN_COMPONENT_BASE: 'src/app/components',
  GEN_SERVICE_BASE:   'src/app/core/services',
  GEN_GUARD_BASE:     'src/app/core/guards',
  GEN_PIPE_BASE:      'src/app/core/pipes',
  GEN_TYPES:          'feature,page,layout,ui',
  GEN_PREFIX:         'app',
  GEN_STYLE_EXT:      'scss',
};

function loadToolsConfig(projectRoot) {
  const config = { ...DEFAULT_CONFIG };
  const toolsFile = path.join(projectRoot, '.tools');
  if (!fs.existsSync(toolsFile)) return { config, source: null };

  const lines = fs.readFileSync(toolsFile, 'utf8').split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    if (!Object.prototype.hasOwnProperty.call(DEFAULT_CONFIG, key)) continue;
    let value = trimmed.slice(eq + 1).trim();
    // strip matching surrounding quotes
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    config[key] = value;
  }
  return { config, source: toolsFile };
}

const { config, source: configSource } = loadToolsConfig(root);

const COMPONENT_BASE = path.join(root, config.GEN_COMPONENT_BASE);
const SERVICE_BASE   = path.join(root, config.GEN_SERVICE_BASE);
const GUARD_BASE      = path.join(root, config.GEN_GUARD_BASE);
const PIPE_BASE       = path.join(root, config.GEN_PIPE_BASE);
const STYLE_EXT       = config.GEN_STYLE_EXT.replace(/^\./, '');
const SELECTOR_PREFIX = config.GEN_PREFIX;
const CC_TYPES = config.GEN_TYPES
  .split(',')
  .map(t => t.trim())
  .filter(Boolean);

// ── Name utilities ────────────────────────────────────────────────────────────

function toPascalCase(s) {
  if (/^[A-Z]/.test(s) && !s.includes('-') && !s.includes('_')) return s;
  return s.split(/[-_/]/).map(p => p.charAt(0).toUpperCase() + p.slice(1)).join('');
}

function toCamelCase(s) {
  const pascal = toPascalCase(s);
  return pascal.charAt(0).toLowerCase() + pascal.slice(1);
}

function toSelector(s) {
  const kebab = s.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/^-/, '').replace(/--+/g, '-');
  return `${SELECTOR_PREFIX}-${kebab}`;
}

function parsePath(input) {
  const normalised = input.replace(/\\/g, '/').replace(/\/+$/, '');
  const segments = normalised.split('/');
  const dirName = segments[segments.length - 1];
  return { segments, dirName };
}

function resolveClassName(dirName, customName) {
  if (customName) return toPascalCase(customName);
  return toPascalCase(dirName);
}

// ── File writing ──────────────────────────────────────────────────────────────

function write(filePath, content) {
  if (isDry) { dryLog(path.relative(root, filePath)); return; }
  if (fs.existsSync(filePath) && !isForce) { skip(path.relative(root, filePath)); return; }
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, 'utf8');
  ok(path.relative(root, filePath));
}

// ── Templates ─────────────────────────────────────────────────────────────────

function componentTs(className, withScss) {
  const selector  = toSelector(className);
  const styleUrls = withScss ? `\n  styleUrls:   ['./index.${STYLE_EXT}'],` : '';
  return `import {
  Component,
  ChangeDetectionStrategy,
  signal,
  inject,
} from '@angular/core';

@Component({
  selector:    '${selector}',
  standalone:  true,
  imports:     [],
  templateUrl: './index.html',${styleUrls}
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ${className}Component {
  // inject(SomeService)
  // someSignal = signal<string>('');
}
`;
}

function componentHtml(className) {
  const selector = toSelector(className);
  return `<!-- ${selector} -->\n<div class="">\n\n</div>\n`;
}

function componentScss(className) {
  const selector = toSelector(className);
  return `// ${selector}\n// Component-scoped styles (prefer Tailwind utilities in the template).\n`;
}

function serviceTs(className) {
  return `import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Injectable({ providedIn: 'root' })
export class ${className}Service {
  private http = inject(HttpClient);

  // Example:
  // private _data = signal<unknown[]>([]);
  // readonly data = this._data.asReadonly();
}
`;
}

function guardTs(className, dirName) {
  const exportName = toCamelCase(className) + 'Guard';
  return `import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
// import { ${className}Service } from '../services/${dirName}.service';

export const ${exportName}: CanActivateFn = (_route, _state) => {
  const router = inject(Router);
  // const auth = inject(${className}Service);
  // if (auth.isAuthenticated()) return true;
  // return router.createUrlTree(['/login']);
  return true;
};
`;
}

function pipeTs(className) {
  const pipeName = toCamelCase(className);
  return `import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: '${pipeName}', standalone: true })
export class ${className}Pipe implements PipeTransform {
  transform(value: unknown, ...args: unknown[]): unknown {
    return value;
  }
}
`;
}

// ── Header ────────────────────────────────────────────────────────────────────

console.log(`\n  ${c.bold}gen.mjs${c.reset}  ${c.gray}${isDry ? '[dry run] ' : ''}${c.reset}`);
console.log(`  ${c.dim}root:   ${root}${c.reset}`);
console.log(`  ${c.dim}config: ${configSource ? path.relative(root, configSource) : '(defaults — no .tools found)'}${c.reset}`);

// ── Dispatch ──────────────────────────────────────────────────────────────────

if (isService || isGuard || isPipe) {
  const rawPathArg = posArgs[0];
  if (!rawPathArg) fatal('Missing <path> for --service / --guard / --pipe.');
  const { segments, dirName } = parsePath(rawPathArg);
  const className = resolveClassName(dirName, customName);

  if (customName) info(`class name overridden: ${c.reset}${c.bold}${className}${c.reset}${c.dim} (folder: ${dirName})`);
  console.log('');

  if (isService) {
    write(path.join(SERVICE_BASE, ...segments.slice(0, -1), `${dirName}.service.ts`), serviceTs(className));
  } else if (isGuard) {
    write(path.join(GUARD_BASE, ...segments.slice(0, -1), `${dirName}.guard.ts`), guardTs(className, dirName));
  } else {
    write(path.join(PIPE_BASE, ...segments.slice(0, -1), `${dirName}.pipe.ts`), pipeTs(className));
  }

} else {
  // Component: CC mode (<type> <name>) vs legacy free-path mode (<path>)
  const first = posArgs[0];
  const isCcMode = CC_TYPES.includes(first) && posArgs.length >= 2;

  let compDir, dirName, className;

  if (isCcMode) {
    const type = first;
    const name = posArgs[1];
    if (!/^[a-z][a-z0-9-]*$/.test(name)) fatal(`Name must be kebab-case (e.g. my-component) — got "${name}"`);
    dirName = name;
    className = resolveClassName(dirName, customName);
    compDir = path.join(COMPONENT_BASE, type, name);
    info(`Capsule Convention mode: type=${type}, name=${name}`);
  } else {
    if (CC_TYPES.length && !CC_TYPES.includes(first)) {
      info(`"${first}" isn't a configured type (${CC_TYPES.join(', ')}) — falling back to free-path mode`);
    }
    const rawPathArg = posArgs[0];
    const parsed = parsePath(rawPathArg);
    dirName = parsed.dirName;
    className = resolveClassName(dirName, customName);
    compDir = rawPathArg.startsWith('src/') || rawPathArg.startsWith('app/')
      ? path.join(root, rawPathArg)
      : path.join(COMPONENT_BASE, ...parsed.segments);
  }

  if (customName) info(`class name overridden: ${c.reset}${c.bold}${className}${c.reset}${c.dim} (folder: ${dirName})`);
  console.log('');

  write(path.join(compDir, 'index.ts'),   componentTs(className, withScss));
  write(path.join(compDir, 'index.html'), componentHtml(className));
  if (withScss) write(path.join(compDir, `index.${STYLE_EXT}`), componentScss(className));
}

console.log('');

