export function chromeLaunchArgs() {
  // Let Chrome use the host GPU by default. SwiftShader remains a portable
  // fallback for machines whose headless GPU process cannot initialise.
  const backend = process.env.WATERFALL_GPU_BACKEND || 'default';
  if (!['swiftshader', 'metal', 'default'].includes(backend)) {
    throw new Error(`Unknown WATERFALL_GPU_BACKEND: ${backend}`);
  }
  const args = ['--enable-webgl', '--disable-dev-shm-usage'];
  if (backend !== 'default') args.push('--use-gl=angle', `--use-angle=${backend}`);
  return args;
}
