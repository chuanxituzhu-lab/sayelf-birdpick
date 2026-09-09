/**
 * 评价工作流·加权求和引擎
 * 只读 photos 表的结构化事实数据 + 模板权重，不调用任何AI模型——
 * 语义标签(semantic_tags)由云端调用产出后已经写进 photos 表，这里直接读，不重新调用。
 * 因为不联网、不调模型，这一步可以随时切模板、实时看排序结果。
 */
import Database from 'better-sqlite3';

/**
 * @param {string} dbPath SQLite 数据库路径
 * @param {object} template 评分模板 { weights: {...}, tagBonus: {...} }
 * @returns {Array<{id:number, filePath:string, totalScore:number, breakdown:object}>}
 *   按 totalScore 降序排列
 */
export function scorePhotos(dbPath, template) {
  const db = new Database(dbPath, { readonly: true });

  // reject 桶不参与评分排序（只分级不删除，但不进候选列表）；
  // 连拍去重后的非代表帧(is_duplicate_frame=1)也不重复出现在候选里
  const rows = db.prepare(`
    SELECT id, file_path, sharpness_score, eye_sharpness_ratio,
           subject_area_ratio, background_clutter, semantic_tags, tech_grade
    FROM photos
    WHERE tech_grade != 'reject' AND is_duplicate_frame = 0
  `).all();

  db.close();

  const { weights, tagBonus = {} } = template;

  const scored = rows.map((row) => {
    const tags = row.semantic_tags ? JSON.parse(row.semantic_tags) : [];

    const breakdown = {
      sharpness: normalize(row.sharpness_score, 0, 2000) * (weights.sharpness ?? 0),
      eyeSharpness: (row.eye_sharpness_ratio ?? 0) * (weights.eyeSharpness ?? 0),
      subjectSize: normalize(row.subject_area_ratio, 0, 1) * (weights.subjectSize ?? 0),
      backgroundClean: (1 - normalize(row.background_clutter, 0, 1)) * (weights.backgroundClean ?? 0),
      tagBonus: tags.reduce((sum, tag) => sum + (tagBonus[tag] ?? 0), 0),
    };

    const totalScore = Object.values(breakdown).reduce((a, b) => a + b, 0);

    return {
      id: row.id,
      filePath: row.file_path,
      totalScore: Math.round(totalScore * 100) / 100,
      breakdown,
    };
  });

  scored.sort((a, b) => b.totalScore - a.totalScore);
  return scored;
}

/** 把 value 线性归一化到 0-1 区间，null/undefined 一律按0处理 */
function normalize(value, min, max) {
  if (value === null || value === undefined) return 0;
  const clamped = Math.min(Math.max(value, min), max);
  return (clamped - min) / (max - min);
}
