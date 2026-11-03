import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const source =
  process.argv[2]?.trim() ||
  process.env.OPENAPI_SOURCE?.trim() ||
  'http://localhost:8000/openapi.json'
const root = fileURLToPath(new URL('../', import.meta.url))
const cli = fileURLToPath(new URL('../node_modules/openapi-typescript/bin/cli.js', import.meta.url))
const result = spawnSync(process.execPath, [cli, source, '-o', 'src/shared/api/schema.d.ts'], {
  cwd: root,
  stdio: 'inherit',
})

if (result.error) console.error(result.error.message)
process.exit(result.status ?? 1)
