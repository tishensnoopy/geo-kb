#!/usr/bin/env python3
"""安装 geo-kb 工作台。

用户说「安装这个项目」时，Agent 运行本脚本完成安装。不联网、不装依赖、
不修改用户已有文件，只在指定目录内创建或更新 geo-kb 目录。

用法：
    python3 scripts/install.py                 # 装到当前目录
    python3 scripts/install.py --target <目录>  # 装到指定目录
    python3 scripts/install.py --check          # 只检查安装状态，不改文件

安装完成后会做三件事：
    1. 复制 SKILL.md / reference/ / templates/ / workbench.html 到目标目录
    2. 创建 data/ 空目录（用户数据由 Agent 后续写入）
    3. 在项目根写或更新 AGENTS.md 片段，让二次启动能找到工作台
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "geo-kb"
MARKER_START = "<!-- geo-kb:begin -->"
MARKER_END = "<!-- geo-kb:end -->"
CST = timezone(timedelta(hours=8))


def read_version() -> str:
    """从 SKILL.md frontmatter 读版本号，读不到就标unknown。"""
    skill = ROOT / "SKILL.md"
    if not skill.exists():
        return "unknown"
    for line in skill.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return "unknown"


def check(target: Path) -> int:
    """检查安装状态。不写任何文件。"""
    base = target / SKILL_NAME
    if not base.exists():
        print(json.dumps({
            "installed": False,
            "reason": f"{base} 不存在",
            "expected_dir": str(base),
        }, ensure_ascii=False))
        return 1

    info_file = base / ".安装信息.json"
    info = {}
    if info_file.exists():
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
        except Exception:
            info = {}

    wb = base / "workbench.html"
    data = base / "data"
    data_dirs = []
    if data.exists():
        data_dirs = [p.name for p in data.iterdir() if p.is_dir()]

    out = {
        "installed": True,
        "base": str(base),
        "workbench": str(wb) if wb.exists() else None,
        "workbench_exists": wb.exists(),
        "data_dir": str(data) if data.exists() else None,
        "companies": data_dirs,
        "installed_at": info.get("installed_at"),
        "installed_version": info.get("version"),
        "repo_version": read_version(),
        "needs_update": info.get("version") != read_version(),
    }
    # next_actions：装完 Agent 必须马上做的事。写进输出而不是靠 Agent 自觉。
    na = []
    if not data_dirs:
        na.append("还没有任何企业数据。把工作台绝对路径告诉用户，请他在浏览器里打开。")
        na.append(
            "问用户要第一家企业的基本信息（企业名称、品牌名、官网、主营业务、地区、"
            "这次最想解决什么），拿到后在 data/<企业简称>/ 建六份 JSON（照 templates/json/ 的模板）。"
        )
    else:
        na.append(
            f"已有 {len(data_dirs)} 家企业：{'、'.join(data_dirs)}。"
            f"开工前先读对应企业的 JSON，不要凭记忆回答。"
        )
        na.append("检查各企业的 待办.json，把已到期的条目列给用户。")
    na.append("探测连接器并写入 环境状态.json（模板在 templates/json/）。页面在浏览器沙箱里探测不到 MCP。")
    na.append(
        "没连任何知识库工具时主动说明后果（成果停本机、内容团队拿不到、知识库不会自动更新），"
        "并给替代路径：导出 Markdown 永远可用；Obsidian vault 是本机文件夹，不需要连接器。"
    )
    na.append(
        "问用户要不要按这家企业的复核周期建定时提醒任务。同意就用定时任务能力真建出来，"
        "不要只在 JSON 里标个字段就算完成。"
    )
    if info.get("version") != read_version():
        na.append(
            f"版本不一致：已装 {info.get('version')}，仓库 {read_version()}。提醒用户重跑安装脚本。"
        )
    out["next_actions"] = na
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if wb.exists() else 2


def write_agents_md(target: Path, base: Path, version: str) -> str:
    """在项目根写/更新 AGENTS.md 片段。这是二次启动能找到工作台的关键。"""
    agents = target / "AGENTS.md"
    block = f"""{MARKER_START}
## geo-kb 企业知识库工作台

本项目装了 geo-kb，用来给企业建AI 能准确复述的事实库。

**工作台位置**：`{base / 'workbench.html'}`
**数据位置**：`{base / 'data'}/`（每家企业一个子目录，JSON 文件）
**安装版本**：{version} · {datetime.now(CST).strftime('%Y-%m-%d')}

### 每次开工前先跑这个命令，不要凭记忆回答

用户提到「GEO」「知识库」「事实库」或某家企业名时，先执行：

```bash
python3 {base / 'scripts' / 'install.py'} --check --target {target}
```

它会返回有哪些企业、工作台在哪、哪些条目到期、有没有版本更新。
**输出里的 `next_actions` 是必须执行的动作，不是建议。**

### 新建一家企业

在 `{base / 'data'}/` 下新建 `<企业简称>/`，照 `templates/json/` 的模板建六个 JSON：
`档案.json` `意图.json` `事实.json` `外部说法.json` `待办.json` `更新记录.json`

完整流程见 `{base / 'SKILL.md'}`。

### 同步到用户的知识库工具

**页面在浏览器沙箱里探测不到 MCP 连接器**，所以每次会话开始要先探测，
把结果写入 `{base / '环境状态.json'}`（模板在 `templates/json/`），页面才画得出哪些目标可用。

探测完按可用性处理：

- 有可用目标：对比 `事实.json` 的 `updated_at` 与 `上次同步时间`，有变动就写入，不用等用户下指令
- 全都不可用：明确告诉用户缺什么、怎么获得，并说明后果（成果停本机、内容团队拿不到、
  知识库不会自动更新）。替代路径是导出 Markdown，永远可用；Obsidian vault 是本机文件夹，
  **不需要任何连接器**。

不要静默失败，也不要假装同步成功。

### 定时提醒

按每家企业自己的复核周期分别设定，不要统一成每周。用户的 Agent 有定时任务能力，
**用户同意就真建出来**，不要只在 `待办.json` 里标个字段就算完成。

{MARKER_END}"""

    existing = agents.read_text(encoding="utf-8") if agents.exists() else ""
    if MARKER_START in existing and MARKER_END in existing:
        head = existing.split(MARKER_START)[0]
        tail = existing.split(MARKER_END)[1]
        agents.write_text(head + block + tail, encoding="utf-8")
        return "updated"
    if existing.strip():
        agents.write_text(existing.rstrip() + "\n\n" + block + "\n", encoding="utf-8")
        return "appended"
    agents.write_text(block + "\n", encoding="utf-8")
    return "created"


def install(target: Path) -> int:
    version = read_version()
    base = target / SKILL_NAME
    copied, skipped = [], []

    def cp(src: Path, rel: str):
        dst = base / rel
        if dst.exists():
            skipped.append(rel)
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)

    base.mkdir(parents=True, exist_ok=True)
    cp(ROOT / "SKILL.md", "SKILL.md")
    cp(ROOT / "site" / "workbench.html", "workbench.html")
    for src in sorted((ROOT / "reference").glob("*.md")):
        cp(src, f"reference/{src.name}")
    # 模板分两处：md/ 放给人看的填写说明，json/ 放给 Agent 和页面读的结构
    for src in sorted((ROOT / "templates" / "md").glob("*.md")):
        cp(src, f"templates/md/{src.name}")
    for src in sorted((ROOT / "templates" / "json").glob("*.json")):
        cp(src, f"templates/json/{src.name}")

    # data/ 只放企业子目录，模板不拷进去——Agent 建新企业时从 templates/json/ 复制
    (base / "data").mkdir(exist_ok=True)
    (base / "data" / ".说明.txt").write_text(
        "本目录每家企业一个子目录，存放该企业的六个 JSON 文件。\n"
        "新建企业时：复制 geo-kb/templates/json/ 下的文件到新建的子目录里。\n"
        "环境状态.json 由 Agent 探测连接器后写入，页面读它显示各目标可用性。\n",
        encoding="utf-8")

    # 连接器状态：装完先给一份「未探测」状态，Agent 探测后覆盖
    env_src = base / "环境状态.json"
    if not env_src.exists():
        shutil.copy2(ROOT / "templates" / "json" / "环境状态.json", env_src)

    info = {
        "installed_at": datetime.now(CST).isoformat(timespec="seconds"),
        "version": version,
        "repo": "https://github.com/tishensnoopy/geo-kb",
        "files": sorted(copied),
    }
    (base / ".安装信息.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    agents_state = write_agents_md(target, base, version)
    companies = [p.name for p in (base / "data").iterdir() if p.is_dir()]

    print(json.dumps({
        "ok": True,
        "base": str(base),
        "workbench": str(base / "workbench.html"),
        "data_dir": str(base / "data"),
        "env_status": str(base / "环境状态.json"),
        "copied": copied,
        "skipped_existing": skipped,
        "companies": companies,
        "agents_md": str(target / "AGENTS.md"),
        "agents_md_action": agents_state,
        "version": version,
        "next_actions": [
            "把工作台绝对路径告诉用户，并说明数据在 data/<企业简称>/ 下的六个 JSON 文件里。",
            "探测连接器并写入 环境状态.json，见 README 的「给 Agent 的安装指令」第 3 步。",
            "问用户要不要建定时提醒任务（按每家企业自己的复核周期，不是统一每周）。",
        ],
    }, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="安装 geo-kb 工作台")
    ap.add_argument("--target", default=".", help="安装目标目录，默认当前目录")
    ap.add_argument("--check", action="store_true", help="只检查，不改文件")
    args = ap.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not target.exists():
        print(json.dumps({"error": f"目标目录不存在：{target}"}, ensure_ascii=False))
        return 1

    if args.check:
        return check(target)
    return install(target)


if __name__ == "__main__":
    sys.exit(main())