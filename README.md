# sayelf-birdpick · 识别/评价工作流代码

对应架构文档《sayelf-birdpick-架构文档.md》第1-3节。这一版实现了识别工作流(Python)
和评价工作流(Node)的核心逻辑，云端(语义标注/AI复核)、配额计费、桌面壳HTML界面还没写，
按之前定的顺序，界面之前已经讨论过交互设计，代码留到确认要写的时候再补。

## 许可证与第三方组件

本仓库的许可证按组件划分，不能将下列内容视为同一套 MIT 授权：

### 本仓库自有代码：MIT License

除下述第三方组件外，本仓库由 sayelf 编写的原创代码、脚本、配置和文档采用 MIT License，详见 [LICENSE](LICENSE)。

### RF-DETR 相关部分：Apache License 2.0

本项目通过 `requirements.txt` 使用 RF-DETR 的 `rfdetr` Python 包。RF-DETR 上游开源包及其标注为 Apache 的相关组件遵循 Apache License 2.0；该许可证边界不因本仓库的 MIT 声明而改变。归属声明和许可证链接见 [NOTICE](NOTICE)。RF-DETR 的 Plus 组件或其他未在本项目中分发的组件可能适用不同条款，请以其上游声明为准。

### 模型权重不包含在本仓库内

本仓库不包含 COCO 预训练权重、鸟类/眼部微调权重或其他模型权重文件。运行时可能由 RF-DETR 从其上游来源下载/缓存默认权重，也可以通过 `SAYELF_BIRD_DETECTION_MODEL_PATH` 和 `SAYELF_BIRD_EYE_MODEL_PATH` 指向用户自行获取的本地权重。模型权重需要另行获取或下载，并由使用者自行确认和遵守对应的许可证、来源及使用条款；本仓库的 MIT License 不覆盖这些权重。

## 目录

```
sayelf-birdpick/
├── requirements.txt          # Python依赖
├── package.json              # Node依赖
├── data/
│   └── schema.sql            # SQLite建表脚本
└── src/
    ├── recognition/           # 识别工作流(Python)
    │   ├── quality.py         # 清晰度/曝光
    │   ├── dedup.py           # 连拍去重
    │   ├── detect.py          # RF-DETR主体检测+眼部关键点
    │   ├── eye_focus.py       # 眼部合焦比例（核心价值层）
    │   └── pipeline.py        # 主流程编排，写入SQLite
    └── evaluation/             # 评价工作流(Node)
        ├── scorer.mjs          # 加权求和引擎
        ├── score-demo.mjs      # 命令行验证脚本
        └── templates/          # 三套冷启动种子模板
```

## 安装

```bash
# Python 侧（识别工作流）
pip install -r requirements.txt

# Node 侧（评价工作流）
npm install
```

## 跑通识别工作流

```bash
# 把测试照片放进一个文件夹，比如 D:\test-photos
python -m src.recognition.pipeline D:\test-photos data\photos.db
```

跑完之后 `data/photos.db` 里的 `photos` 表会有每张照片的清晰度、曝光、主体检测框、
眼部合焦比例、连拍分组、三段式分级(`tech_grade`)。这一步**完全不联网**，微调后的
检测/关键点模型权重训练好之前，会自动退回 RF-DETR 的 COCO 预训练权重——能跑通，
但检出率和眼部定位精度会明显低于微调后的效果，这是预期之内的，不是bug。

## 跑通评价工作流

```bash
node src/evaluation/score-demo.mjs data/photos.db national-geographic
```

会打印按"国家地理风"模板打分排序后的前20张照片路径和分数。换成 `tangshui` 或
`ecological-record` 可以看同一批照片在不同审美模板下排序会怎么变。

## 现在能跑通、但还没到生产可用的地方

- **检测/关键点模型还没微调**：用的是COCO通用权重，鸟类检出精度和眼部定位精度有限，
  按上次讨论的顺序，需要先用CVAT标一批群友照片(100-200张)微调后替换
- **三段式分级阈值是冷启动默认值**（`pipeline.py` 里的 `SHARPNESS_PASS` 等几个常量），
  没有用真实标注数据校准过，先能跑通验证代码逻辑，不代表这几个数字是准的
- **语义标签(semantic_tags)目前是空的**：评价工作流的 `tagBonus` 部分暂时不会加分，
  因为语义标注(云端多模态大模型调用)这部分代码还没写
- **没有桌面壳界面**：现在是命令行跑通，`index.html`/`review.html` 按上次讨论的交互设计，
  还没写代码
