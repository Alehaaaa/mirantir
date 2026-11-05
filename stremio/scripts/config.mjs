import { readFile, writeFile } from 'node:fs/promises';
const data = JSON.parse(await readFile(new URL('../wrangler.jsonc',import.meta.url),'utf8'));
const id = process.env.CF_D1_DATABASE_ID;
if (id && !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(id))
  throw new Error('CF_D1_DATABASE_ID must be a UUID');
if (process.argv.includes('--production') && !id)
  throw new Error('Set CF_D1_DATABASE_ID from wrangler d1 create');
data.d1_databases[0].database_id = id || '00000000-0000-0000-0000-000000000000';
await writeFile(new URL('../wrangler.generated.jsonc',import.meta.url),
 JSON.stringify(data,null,2)+'\n');
console.log('Generated ignored Wrangler configuration');
