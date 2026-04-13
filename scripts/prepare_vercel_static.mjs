import { cp, mkdir, rm, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = path.resolve(scriptDir, '..');
const sourceDir = path.resolve(workspaceRoot, 'rance-world-note');
const publicDir = path.resolve(workspaceRoot, 'public');
const targetDir = path.resolve(publicDir, 'rance-world-note');

function isWithin(parentDir, targetPath) {
  const relativePath = path.relative(parentDir, targetPath);
  return relativePath === '' || (!relativePath.startsWith('..') && !path.isAbsolute(relativePath));
}

async function assertDirectoryExists(directoryPath, label) {
  let info;
  try {
    info = await stat(directoryPath);
  } catch (error) {
    if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') {
      throw new Error(`${label} not found: ${directoryPath}`);
    }
    throw error;
  }

  if (!info.isDirectory()) {
    throw new Error(`${label} is not a directory: ${directoryPath}`);
  }
}

async function main() {
  await assertDirectoryExists(sourceDir, 'Mirror output');

  if (!isWithin(publicDir, targetDir) || !isWithin(workspaceRoot, publicDir)) {
    throw new Error(`Refusing to write outside the workspace: ${targetDir}`);
  }

  await mkdir(publicDir, { recursive: true });
  await rm(targetDir, { recursive: true, force: true });
  await cp(sourceDir, targetDir, { recursive: true, force: true });

  console.log(`Prepared Vercel static output in ${targetDir}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
