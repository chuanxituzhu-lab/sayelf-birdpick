-- photos：识别工作流产出的结构化事实数据（客观数据，不含任何审美判断）
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    capture_time TEXT,
    burst_group_id INTEGER,
    is_duplicate_frame INTEGER DEFAULT 0,
    sharpness_score REAL,
    exposure_flag TEXT,
    subject_detected INTEGER DEFAULT 0,
    subject_confidence REAL,
    subject_bbox TEXT,
    subject_area_ratio REAL,
    eye_bbox TEXT,
    eye_sharpness_ratio REAL,
    composition_offset REAL,
    background_clutter REAL,
    tech_grade TEXT DEFAULT 'pending',
    audit_status TEXT DEFAULT 'none',
    semantic_tags TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- annotations：历史标注（双线记录，技术合格与否 / 精选与否分开，防止互相污染）
CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id INTEGER NOT NULL REFERENCES photos(id),
    tech_label TEXT DEFAULT 'unlabeled',
    aesthetic_label TEXT DEFAULT 'unlabeled',
    reject_reason TEXT,
    labeled_by TEXT,
    labeled_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- eval_templates：评价工作流的评分模板，source 区分冷启动种子模板还是学出来的专属权重
CREATE TABLE IF NOT EXISTS eval_templates (
    template_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    source TEXT DEFAULT 'seed',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- entitlements：配额状态，不存支付信息
CREATE TABLE IF NOT EXISTS entitlements (
    user_id TEXT PRIMARY KEY,
    tier TEXT DEFAULT 'trial',
    cloud_quota_remaining INTEGER DEFAULT 0,
    quota_reset_at TEXT,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_photos_tech_grade ON photos(tech_grade);
CREATE INDEX IF NOT EXISTS idx_photos_burst_group ON photos(burst_group_id);
CREATE INDEX IF NOT EXISTS idx_annotations_photo_id ON annotations(photo_id);
