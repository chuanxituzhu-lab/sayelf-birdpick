/**
 * 命令行示例：跑通识别流程产出 photos.db 之后，用这个脚本验证评价工作流能不能正常出结果。
 * 用法：node src/evaluation/score-demo.mjs <数据库路径> <模板名，如 national-geographic>
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { scorePhotos } from './scorer.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const [, , dbPathArg, templateNameArg] = process.argv;

if (!dbPathArg || !templateNameArg) {
  console.error('用法: node src/evaluation/score-demo.mjs <数据库路径> <模板名>');
  console.error('模板名可选: national-geographic / tangshui / ecological-record');
  process.exit(1);
}

const templatePath = path.join(__dirname, 'templates', `${templateNameArg}.json`);
if (!fs.existsSync(templatePath)) {
  console.error(`找不到模板文件: ${templatePath}`);
  process.exit(1);
}

const template = JSON.parse(fs.readFileSync(templatePath, 'utf-8'));
const results = scorePhotos(dbPathArg, template);

console.log(`模板: ${template.name}，候选照片 ${results.length} 张，按分数从高到低：`);
results.slice(0, 20).forEach((r, i) => {
  console.log(`${i + 1}. [${r.totalScore}] ${r.filePath}`);
});
