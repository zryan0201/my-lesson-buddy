import {build} from 'esbuild';
import {mkdir,copyFile,readdir,readFile,stat} from 'node:fs/promises';
import path from 'node:path';
const root=process.cwd();
await mkdir('dist/vendor/ort',{recursive:true});
// Use the official browser distribution; the raw source also imports Node-only image modules.
await build({entryPoints:['node_modules/@huggingface/transformers/dist/transformers.web.min.js'],outfile:'dist/vendor/transformers.js',bundle:true,format:'esm',platform:'browser',minify:true,conditions:['browser'],logLevel:'warning'});
await build({entryPoints:['node_modules/fflate/esm/browser.js'],outfile:'dist/vendor/fflate.js',bundle:true,format:'esm',platform:'browser',minify:true});
const ort='node_modules/onnxruntime-web/dist';
for(const name of await readdir(ort))if(/^ort-wasm.*\.(?:wasm|mjs)$/.test(name))await copyFile(path.join(ort,name),path.join('dist/vendor/ort',name));
const manifest=JSON.parse(await readFile('dist/audio/manifest.json','utf8'));
for(const clip of Object.values(manifest)){if(!(await stat(path.join('dist/audio',clip.file))).size)throw new Error('Empty narration asset.');}
console.log('Built browser AI and package libraries; verified '+Object.keys(manifest).length+' narration assets.');
